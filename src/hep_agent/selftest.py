"""Deterministic installation self-test.

Runs a fixed, LLM-free trial workflow through the full deterministic toolchain
(MadGraph -> Pythia8 -> Delphes -> MadAnalysis) to verify these tools are
installed and working end to end. No planner, repair, or model call is
involved: the workflow is constructed in code, so this is a pure installation
cross-check.

It reuses exactly the deterministic execution and analysis stages the agent
runs after approval, so a passing self-test means the same machinery a real run
depends on is working.
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class StageOutcome:
    """Pass/fail outcome for one tool in the toolchain."""

    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class SelfTestResult:
    """Overall installation self-test result."""

    success: bool
    stages: list[StageOutcome] = field(default_factory=list)
    run_directory: Path | None = None
    cross_section_pb: float | None = None
    event_count: int | None = None


# A fixed, well-supported trial process: Drell-Yan electron-pair production at
# the LHC, with every downstream stage enabled.
def build_selftest_workflow(*, nevents: int = 1000) -> WorkflowIntent:
    """Construct the fixed trial workflow with all pipeline stages enabled."""

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
            pythia8=True,
            delphes=True,
            madanalysis=True,
        ),
    )


def run_installation_selftest(
    *,
    mg5_executable: str | Path,
    madanalysis_executable: str | Path | None = None,
    nevents: int = 1000,
    run_directory: str | Path = "results/selftest",
    timeout_seconds: float = 1800,
    analysis_timeout_seconds: float = 300,
) -> SelfTestResult:
    """Run the fixed trial workflow and report per-tool installation health.

    This never calls a model. It builds a deterministic artifact and runs the
    same execution and analysis stages the agent uses after approval.
    """

    workflow = build_selftest_workflow(nevents=nevents)
    artifact = build_madgraph_workflow_artifact(workflow)

    run_dir = Path(run_directory)
    execution = run_madgraph_workflow(
        artifact,
        mg5_executable=mg5_executable,
        run_directory=run_dir,
        timeout_seconds=timeout_seconds,
    )

    physics = None
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

    # MadGraph: process generated and events produced.
    if execution.success and valid and physics is not None:
        mg_detail = (
            f"Ran and produced events "
            f"({physics.event_count if physics.event_count else 'unknown'} "
            f"events)."
        )
        mg_ok = physics.primary_lhe_file is not None
        if not mg_ok:
            mg_detail = "Ran, but no LHE event file was found."
    else:
        mg_ok = False
        mg_detail = (
            execution.failure_message
            or "MadGraph did not produce valid physics output."
        )
    stages.append(StageOutcome("MadGraph", mg_ok, mg_detail))

    # Pythia8: showered HepMC output present.
    hepmc = physics.showered_hepmc_file if physics is not None else None
    py_ok = hepmc is not None and Path(hepmc).exists()
    stages.append(
        StageOutcome(
            "Pythia8",
            py_ok,
            "Parton shower produced HepMC output."
            if py_ok
            else "No showered HepMC output was produced.",
        )
    )

    # Delphes: detector ROOT output present.
    root = physics.detector_root_file if physics is not None else None
    dl_ok = root is not None and Path(root).exists()
    stages.append(
        StageOutcome(
            "Delphes",
            dl_ok,
            "Detector simulation produced ROOT output."
            if dl_ok
            else "No detector ROOT output was produced.",
        )
    )

    # MadAnalysis: run the deterministic MA5 stage.
    analysis = None
    if valid and physics is not None:
        analysis = run_madanalysis_stage(
            workflow,
            physics,
            madanalysis_executable=madanalysis_executable,
            analysis_directory=run_dir / "analysis",
            timeout_seconds=analysis_timeout_seconds,
        )
    if analysis is not None and analysis.success:
        ma_ok = True
        ma_detail = "MadAnalysis produced a report."
    else:
        ma_ok = False
        ma_detail = (
            analysis.failure_message
            if analysis is not None and analysis.failure_message
            else "MadAnalysis did not run (MadGraph output was not valid)."
        )
    stages.append(StageOutcome("MadAnalysis", ma_ok, ma_detail))

    success = all(stage.ok for stage in stages)

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

    parser = argparse.ArgumentParser(
        description=(
            "Deterministic installation self-test: runs a fixed trial "
            "process with Pythia8, Delphes, and MadAnalysis enabled. No "
            "model is involved."
        )
    )
    parser.add_argument(
        "--mg5",
        default=None,
        help="Path to the mg5_aMC executable "
        "(default: from configs/local_paths.json).",
    )
    parser.add_argument(
        "--ma5",
        default=None,
        help="Path to the ma5 executable "
        "(default: from configs/local_paths.json).",
    )
    parser.add_argument("--events", type=int, default=1000)
    parser.add_argument("--run-dir", default="results/selftest")
    parser.add_argument(
        "--local-paths", default="configs/local_paths.json"
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

    print("=== HEP Local Agent installation self-test ===")
    print("Trial process : generate p p > e+ e-")
    print(f"Events        : {args.events}")
    print("Stages        : MadGraph + Pythia8 + Delphes + MadAnalysis")
    print("Model involved: none (deterministic)\n")
    print("Running the toolchain; this may take a few minutes...\n")

    result = run_installation_selftest(
        mg5_executable=mg5,
        madanalysis_executable=ma5,
        nevents=args.events,
        run_directory=args.run_dir,
    )

    for stage in result.stages:
        marker = "OK  " if stage.ok else "FAIL"
        print(f"  [{marker}] {stage.name}: {stage.detail}")

    if result.cross_section_pb is not None:
        print(
            f"\n  cross section: {result.cross_section_pb} pb, "
            f"events: {result.event_count}"
        )

    print(f"\nRESULT: {'PASS' if result.success else 'FAIL'}")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
