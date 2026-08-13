"""Deterministic, tool-aware installation self-test.

Runs a fixed, LLM-free trial workflow through the deterministic toolchain
(MadGraph -> Pythia8 -> Delphes -> MadAnalysis) to verify these tools are
installed and working end to end. No planner, repair, or model call is
involved: the workflow is constructed in code.

The agent does not bundle these tools; it orchestrates an existing MadGraph
install. MadGraph normally places Pythia8 and MadAnalysis under ``HEPTools``,
while Delphes may be installed either at the MadGraph root or under
``HEPTools``. This self-test therefore first *detects* which of those tools the
selected MadGraph actually has, and only exercises the ones present - so a
tool that is simply not installed is reported distinctly from a tool that ran
and failed, and a missing downstream tool cannot sabotage an installed one.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from hep_agent.builders import build_madgraph_workflow_artifact
from hep_agent.execution.madgraph_runner import run_madgraph_workflow
from hep_agent.execution.outcome import (
    execution_has_valid_physics_output,
)
from hep_agent.execution.result_parser import parse_madgraph_result
from hep_agent.orchestration.analysis_stage import run_madanalysis_stage
from hep_agent.schemas import (
    BeamSpec,
    ColliderSpec,
    ColliderType,
    EnergyMeaning,
    EnergySpec,
    ModelSource,
    ParticleNode,
    PhysicsModelSpec,
    PipelineSpec,
    ProcessSpec,
    RunSettings,
    TaskType,
    WorkflowIntent,
)

# Stage status values.
OK = "ok"
FAILED = "failed"
MISSING = "missing"
SKIPPED = "skipped"


def _prepare_macos_runtime_environment(
    *,
    python_prefix: str | Path | None = None,
    platform_name: str | None = None,
) -> None:
    """Select the managed macOS ROOT without leaking Conda-base tools.

    The self-test is commonly launched as ``.venv/bin/python -m ...`` rather
    than through ``run_agent.sh``.  In that case the interpreter is correct,
    but the inherited PATH can still select Homebrew ROOT and Conda-base can
    provide XML for a different Pythia version.  Normalize only when this
    Python prefix actually contains the managed ROOT installation.
    """

    active_platform = platform_name or sys.platform
    if active_platform != "darwin":
        return

    prefix = Path(python_prefix or sys.prefix).expanduser().resolve()
    root_config = prefix / "bin" / "root-config"
    if not root_config.is_file() or not os.access(root_config, os.X_OK):
        return

    os.environ["ROOTSYS"] = str(prefix)
    existing_path = os.environ.get("PATH", "")
    os.environ["PATH"] = (
        f"{prefix / 'bin'}:{existing_path}"
        if existing_path
        else str(prefix / "bin")
    )

    for variable in (
        "DYLD_LIBRARY_PATH",
        "PYTHIA8DATA",
        "CPATH",
        "C_INCLUDE_PATH",
        "CPLUS_INCLUDE_PATH",
        "LIBRARY_PATH",
        "ROOT_INCLUDE_PATH",
    ):
        os.environ.pop(variable, None)


@dataclass(frozen=True)
class StageOutcome:
    """Outcome for one tool: ok / failed / missing (not installed) / skipped."""

    name: str
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == OK


@dataclass(frozen=True)
class SelfTestResult:
    """Overall installation self-test result.

    ``success`` is True when MadGraph ran and no *installed* tool failed. Tools
    that are not installed are warnings, not failures.
    """

    success: bool
    stages: list[StageOutcome] = field(default_factory=list)
    run_directory: Path | None = None
    cross_section_pb: float | None = None
    event_count: int | None = None

    @property
    def missing(self) -> list[str]:
        return [s.name for s in self.stages if s.status == MISSING]


def _mg5_root(mg5_executable: str | Path) -> Path:
    """MadGraph root directory, given the ``bin/mg5_aMC`` executable path."""

    return Path(mg5_executable).resolve().parent.parent


def _has_any(directory: Path, names: list[str]) -> bool:
    return any((directory / name).exists() for name in names)


def detect_tools(
    mg5_executable: str | Path,
    madanalysis_executable: str | Path | None = None,
) -> dict:
    """Detect which downstream tools the selected MadGraph provides."""

    mg5_root = _mg5_root(mg5_executable)
    heptools = mg5_root / "HEPTools"
    ma5 = bool(madanalysis_executable) and Path(
        madanalysis_executable
    ).exists()
    if not ma5:
        ma5 = _has_any(heptools, ["madanalysis5", "MadAnalysis5"])
    return {
        "pythia8": _has_any(
            heptools, ["pythia8", "MG5aMC_PY8_interface"]
        ),
        "delphes": (
            _has_any(mg5_root, ["Delphes", "delphes"])
            or _has_any(heptools, ["Delphes", "delphes"])
        ),
        "madanalysis": ma5,
        "heptools_found": heptools.exists(),
    }


def build_selftest_workflow(
    *,
    nevents: int = 1000,
    pythia8: bool = True,
    delphes: bool = True,
    madanalysis: bool = True,
) -> WorkflowIntent:
    """Construct the fixed trial workflow with the given stages enabled."""

    return WorkflowIntent(
        task_type=TaskType.RUN_SIMULATION,
        model=PhysicsModelSpec(name="sm", source=ModelSource.BUILTIN),
        collider=ColliderSpec(
            collider_type=ColliderType.HADRON,
            beams=[BeamSpec(particle="p"), BeamSpec(particle="p")],
            energy=EnergySpec(
                value_gev=13000.0,
                meaning=EnergyMeaning.TOTAL_CENTER_OF_MASS,
            ),
        ),
        processes=[
            ProcessSpec(
                incoming_particles=["p", "p"],
                final_particles=[
                    ParticleNode(particle="e+"),
                    ParticleNode(particle="e-"),
                ],
            )
        ],
        run=RunSettings(nevents=nevents),
        pipeline=PipelineSpec(
            madgraph=True,
            pythia8=pythia8,
            delphes=delphes,
            madanalysis=madanalysis,
        ),
    )


def _resolve(flag: str, detected: bool) -> tuple[bool, str]:
    """Resolve an auto/on/off flag against detection into (request, reason)."""

    if flag == "on":
        return True, "requested"
    if flag == "off":
        return False, "disabled"
    # auto
    return (detected, "detected" if detected else "missing")


def _diagnose_from_log(log_text: str) -> str | None:
    """Return a human-readable cause for a shower/tool failure, or None.

    Scans the MadGraph log for well-known failure signatures - a Python or
    library version mismatch, a crash, or MadGraph silently disabling the
    shower - so the self-test can explain *why* a tool did not run instead of
    only reporting that it did not.
    """

    if not log_text:
        return None

    lowered = log_text.lower()
    hints: list[str] = []

    match = re.search(
        r"compiletime version ([\d.]+) of module '([^']+)' "
        r"does not match runtime version ([\d.]+)",
        log_text,
    )
    if match:
        hints.append(
            f"a component ({match.group(2)}) was built for Python "
            f"{match.group(1)} but is running under Python {match.group(3)} "
            f"(version mismatch) - run the agent in the Python environment "
            f"the HEP tools were compiled against, or rebuild LHAPDF/Pythia8 "
            f"for this Python"
        )

    if "segmentation fault" in lowered or "core dumped" in lowered:
        hints.append(
            "a component crashed (segmentation fault), commonly an ABI or "
            "version mismatch between Python, LHAPDF, and Pythia8"
        )

    if (
        "shower = off" in lowered or "shower=off" in lowered
    ) and not hints:
        hints.append(
            "MadGraph disabled the shower (shower = OFF), so Pythia8 did not "
            "run - the Pythia8 interface likely failed to load at startup"
        )

    if not hints:
        return None

    return "; ".join(hints) + "."


def run_installation_selftest(
    *,
    mg5_executable: str | Path,
    madanalysis_executable: str | Path | None = None,
    nevents: int = 1000,
    run_directory: str | Path = "results/selftest",
    timeout_seconds: float = 1800,
    analysis_timeout_seconds: float = 300,
    pythia8: str = "auto",
    delphes: str = "auto",
    madanalysis: str = "auto",
) -> SelfTestResult:
    """Run the fixed trial workflow and report per-tool installation health.

    Never calls a model. Only tools detected as installed are exercised (unless
    forced on); missing tools are reported as warnings, not failures.
    """

    detected = detect_tools(mg5_executable, madanalysis_executable)
    py_req, py_reason = _resolve(pythia8, detected["pythia8"])
    dl_req, dl_reason = _resolve(delphes, detected["delphes"])
    ma_req, ma_reason = _resolve(madanalysis, detected["madanalysis"])

    # Delphes runs on showered events; without Pythia it would fail, so do not
    # request it in that case - report it as skipped instead of a false failure.
    delphes_needs_pythia = dl_req and not py_req
    if delphes_needs_pythia:
        dl_req = False

    workflow = build_selftest_workflow(
        nevents=nevents,
        pythia8=py_req,
        delphes=dl_req,
        madanalysis=ma_req,
    )
    artifact = build_madgraph_workflow_artifact(workflow)

    run_dir = Path(run_directory)
    execution = run_madgraph_workflow(
        artifact,
        mg5_executable=mg5_executable,
        run_directory=run_dir,
        timeout_seconds=timeout_seconds,
    )

    physics = None
    stdout_text = ""
    if execution.stdout_path is not None and execution.stdout_path.is_file():
        stdout_text = execution.stdout_path.read_text(
            encoding="utf-8", errors="replace"
        )
        physics = parse_madgraph_result(
            stdout_text=stdout_text,
            execution_directory=run_dir,
        )

    valid = execution_has_valid_physics_output(execution, physics)

    stages: list[StageOutcome] = []

    # MadGraph is always required.
    mg_ok = (
        execution.success
        and valid
        and physics is not None
        and physics.primary_lhe_file is not None
    )
    if mg_ok:
        mg_detail = (
            f"Ran and produced events "
            f"({physics.event_count if physics.event_count else 'unknown'} "
            f"events)."
        )
    else:
        mg_detail = (
            execution.failure_message
            or "MadGraph did not produce valid physics output."
        )
        diagnosis = _diagnose_from_log(stdout_text)
        if diagnosis:
            mg_detail += f" Likely cause: {diagnosis}"
    stages.append(StageOutcome("MadGraph", OK if mg_ok else FAILED, mg_detail))

    # Pythia8.
    if not py_req:
        if py_reason == "disabled":
            stages.append(
                StageOutcome("Pythia8", SKIPPED, "Disabled for this run.")
            )
        else:
            stages.append(
                StageOutcome(
                    "Pythia8",
                    MISSING,
                    "Not installed in this MadGraph (HEPTools/pythia8).",
                )
            )
    else:
        hepmc = physics.showered_hepmc_file if physics is not None else None
        ok = hepmc is not None and Path(hepmc).exists()
        if ok:
            py_detail = "Parton shower produced HepMC output."
        else:
            py_detail = (
                "Installed and requested, but no HepMC output was produced."
            )
            diagnosis = _diagnose_from_log(stdout_text)
            if diagnosis:
                py_detail += f" Likely cause: {diagnosis}"
        stages.append(
            StageOutcome("Pythia8", OK if ok else FAILED, py_detail)
        )

    # Delphes.
    if not dl_req:
        if delphes_needs_pythia:
            stages.append(
                StageOutcome(
                    "Delphes",
                    SKIPPED,
                    "Skipped: needs Pythia8, which was not run.",
                )
            )
        elif dl_reason == "disabled":
            stages.append(
                StageOutcome("Delphes", SKIPPED, "Disabled for this run.")
            )
        else:
            stages.append(
                StageOutcome(
                    "Delphes",
                    MISSING,
                    "Not installed in this MadGraph (checked Delphes and "
                    "HEPTools/Delphes). "
                    "Install from mg5_aMC with: install Delphes",
                )
            )
    else:
        root = physics.detector_root_file if physics is not None else None
        ok = root is not None and Path(root).exists()
        stages.append(
            StageOutcome(
                "Delphes",
                OK if ok else FAILED,
                "Detector simulation produced ROOT output."
                if ok
                else "Installed and requested, but no ROOT output was "
                "produced.",
            )
        )

    # MadAnalysis.
    if not ma_req:
        stages.append(
            StageOutcome(
                "MadAnalysis",
                SKIPPED if ma_reason == "disabled" else MISSING,
                "Disabled for this run."
                if ma_reason == "disabled"
                else "Not installed / not configured.",
            )
        )
    elif not (valid and physics is not None):
        stages.append(
            StageOutcome(
                "MadAnalysis",
                SKIPPED,
                "Skipped: MadGraph output was not valid.",
            )
        )
    else:
        analysis = run_madanalysis_stage(
            workflow,
            physics,
            madanalysis_executable=madanalysis_executable,
            analysis_directory=run_dir / "analysis",
            timeout_seconds=analysis_timeout_seconds,
        )
        if analysis is not None and analysis.success:
            stages.append(
                StageOutcome(
                    "MadAnalysis", OK, "MadAnalysis produced a report."
                )
            )
        else:
            stages.append(
                StageOutcome(
                    "MadAnalysis",
                    FAILED,
                    (
                        analysis.failure_message
                        if analysis is not None
                        and analysis.failure_message
                        else "MadAnalysis was requested but did not "
                        "produce a report."
                    ),
                )
            )

    success = mg_ok and not any(s.status == FAILED for s in stages)

    return SelfTestResult(
        success=success,
        stages=stages,
        run_directory=run_dir,
        cross_section_pb=(
            physics.cross_section_pb if physics is not None else None
        ),
        event_count=physics.event_count if physics is not None else None,
    )


def main(argv: list[str] | None = None) -> int:
    """Headless entry point: ``python -m hep_agent.selftest``."""

    import argparse
    import json

    _prepare_macos_runtime_environment()

    parser = argparse.ArgumentParser(
        description=(
            "Deterministic, tool-aware installation self-test. Runs a fixed "
            "trial process and only exercises the downstream tools your "
            "MadGraph actually has. No model is involved."
        )
    )
    parser.add_argument("--mg5", default=None)
    parser.add_argument("--ma5", default=None)
    parser.add_argument("--events", type=int, default=1000)
    parser.add_argument("--run-dir", default="results/selftest")
    parser.add_argument("--local-paths", default="configs/local_paths.json")
    for stage in ("pythia8", "delphes", "madanalysis"):
        parser.add_argument(
            f"--{stage}",
            choices=("auto", "on", "off"),
            default="auto",
            help=f"{stage}: auto (detect), on (force), off (skip).",
        )
    args = parser.parse_args(argv)

    mg5 = args.mg5
    ma5 = args.ma5
    if mg5 is None or ma5 is None:
        try:
            config = json.loads(Path(args.local_paths).read_text())
        except OSError:
            config = {}
        mg5 = mg5 or config.get("mg5_executable")
        ma5 = ma5 or config.get("madanalysis5_executable")

    if not mg5:
        print(
            "ERROR: no MadGraph executable. Pass --mg5 or set "
            "'mg5_executable' in configs/local_paths.json.",
            file=sys.stderr,
        )
        return 2

    detected = detect_tools(mg5, ma5)
    print("=== HEP Local Agent installation self-test ===")
    print("Trial process : generate p p > e+ e-")
    print(f"Events        : {args.events}")
    print("Model involved: none (deterministic)")
    print(
        "Detected tools: "
        f"Pythia8={'yes' if detected['pythia8'] else 'no'}, "
        f"Delphes={'yes' if detected['delphes'] else 'no'}, "
        f"MadAnalysis={'yes' if detected['madanalysis'] else 'no'}"
    )
    print("\nRunning the toolchain; this may take a few minutes...\n")

    result = run_installation_selftest(
        mg5_executable=mg5,
        madanalysis_executable=ma5,
        nevents=args.events,
        run_directory=args.run_dir,
        pythia8=args.pythia8,
        delphes=args.delphes,
        madanalysis=args.madanalysis,
    )

    labels = {OK: "OK  ", FAILED: "FAIL", MISSING: "MISS", SKIPPED: "SKIP"}
    for stage in result.stages:
        print(f"  [{labels.get(stage.status, '??  ')}] "
              f"{stage.name}: {stage.detail}")

    if result.cross_section_pb is not None:
        print(
            f"\n  cross section: {result.cross_section_pb} pb, "
            f"events: {result.event_count}"
        )

    if result.success and result.missing:
        print(
            f"\nRESULT: PASS (not installed: {', '.join(result.missing)}). "
            "MISS = tool not installed, not a failure."
        )
    else:
        print(f"\nRESULT: {'PASS' if result.success else 'FAIL'}")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
