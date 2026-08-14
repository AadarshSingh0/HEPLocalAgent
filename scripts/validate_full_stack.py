#!/usr/bin/env python3
"""Validate MadGraph, Pythia8, Delphes, and MadAnalysis without Ollama."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from hep_agent.models import AgentProfile, ModelResponse  # noqa: E402
from hep_agent.orchestration import run_end_to_end
from hep_agent.runtime import load_configured_stack, load_stack_manifest  # noqa: E402


def positive_integer(value: str) -> int:
    """Parse a strictly positive command-line integer."""

    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def build_payload(
    *,
    events: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Return the fixed, deterministic full-stack validation workflow."""

    return {
        "schema_version": "1.0",
        "task_type": "run_simulation",
        "model": {
            "name": "sm",
            "source": "builtin",
            "model_path": None,
        },
        "collider": {
            "collider_type": "hadron",
            "beams": [
                {"particle": "p"},
                {"particle": "p"},
            ],
            "energy": {
                "value_gev": 13000,
                "meaning": "total_center_of_mass",
            },
        },
        "processes": [
            {
                "process_id": "dilepton",
                "incoming_particles": ["p", "p"],
                "final_particles": [
                    {
                        "particle": "e+",
                        "decay_products": [],
                    },
                    {
                        "particle": "e-",
                        "decay_products": [],
                    },
                ],
                "required_intermediates": [],
                "excluded_particles": [],
                "coupling_orders": {},
            }
        ],
        "run": {
            "nevents": events,
            "random_seed": 12345,
            "timeout_seconds": timeout_seconds,
            "output_name": "full_stack_dilepton",
        },
        "pipeline": {
            "madgraph": True,
            "pythia8": True,
            "delphes": True,
            "madanalysis": True,
        },
        "field_sources": {},
        "notes": [],
    }


def build_request(events: int) -> str:
    """Return the natural-language request matched by the fixed payload."""

    return (
        "Use the built-in Standard Model to simulate proton-proton "
        "collisions producing an electron and positron at 13 TeV. "
        f"Generate {events} events with MadGraph, shower with Pythia8, "
        "run Delphes, and use MadAnalysis to create default quick-look "
        "plots."
    )


class FixedValidationPlanner:
    """Return the fixed validation workflow without contacting a model."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def chat(self, **_: Any) -> ModelResponse:
        return ModelResponse(
            model="fixed-full-stack-validation",
            content=json.dumps(self.payload),
            total_duration_ns=1,
        )


def load_executable(
    configuration: dict[str, Any],
    key: str,
) -> Path:
    """Load and validate one configured executable."""

    raw_value = configuration.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError(
            f"Missing {key!r} in configs/local_paths.json. "
            "Rerun the installer for the requested HEP tools."
        )

    path = Path(raw_value).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(
            f"Configured executable is not runnable: {path}"
        )
    return path


def existing_file(path: Path | None) -> bool:
    """Whether an optional path identifies a regular file."""

    return path is not None and path.is_file()


def build_parser() -> argparse.ArgumentParser:
    """Construct the command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Run a fixed pp -> e+ e- workflow through MadGraph, "
            "Pythia8, Delphes, and MadAnalysis without contacting Ollama."
        )
    )
    parser.add_argument(
        "--events",
        type=positive_integer,
        default=20,
        help="Number of events to generate (default: 20).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=positive_integer,
        default=3600,
        help="MadGraph workflow timeout (default: 3600).",
    )
    parser.add_argument(
        "--analysis-timeout-seconds",
        type=positive_integer,
        default=600,
        help="MadAnalysis timeout (default: 600).",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=PROJECT_ROOT / "results" / "full_stack_validation",
        help=(
            "Validation output directory "
            "(default: results/full_stack_validation)."
        ),
    )
    parser.add_argument(
        "--paths-config",
        type=Path,
        default=PROJECT_ROOT / "configs" / "local_paths.json",
        help=(
            "Installed-tool path configuration "
            "(default: configs/local_paths.json)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the fixed full-stack workflow and report artifact checks."""

    arguments = build_parser().parse_args(argv)
    configuration_path = arguments.paths_config.expanduser().resolve()

    try:
        configuration = json.loads(
            configuration_path.read_text(encoding="utf-8")
        )
        if not isinstance(configuration, dict):
            raise ValueError("Tool-path configuration must be an object.")
        manifest = load_configured_stack(
            configuration_path, expected_repository_root=PROJECT_ROOT
        )
        stack_manifest = manifest.path
        mg5_executable = manifest.executable("madgraph")
        madanalysis_executable = manifest.executable("madanalysis5")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    output_directory = (
        arguments.output_directory
        .expanduser()
        .resolve()
    )
    output_directory.mkdir(parents=True, exist_ok=True)

    request = build_request(arguments.events)
    payload = build_payload(
        events=arguments.events,
        timeout_seconds=arguments.timeout_seconds,
    )
    profile = AgentProfile(
        primary_model="fixed-full-stack-validation",
        primary_timeout_seconds=30,
        max_repairs=0,
        max_planner_attempts=1,
    )

    print("=" * 72)
    print("HEPLOCALAGENT FULL-STACK VALIDATION")
    print("=" * 72)
    print(f"MadGraph:   {mg5_executable}")
    print(f"MadAnalysis: {madanalysis_executable}")
    print(f"Output:      {output_directory}")
    print("Planner:     fixed local validation payload (Ollama is not used)")

    result = run_end_to_end(
        request,
        client=FixedValidationPlanner(payload),
        profile_name="full_stack_validation",
        profile=profile,
        mg5_executable=mg5_executable,
        madanalysis_executable=madanalysis_executable,
        approval_resolver=lambda _: True,
        records_directory=output_directory / "runs",
        executions_directory=output_directory / "executions",
        analyses_directory=output_directory / "analyses",
        project_root=PROJECT_ROOT,
        analysis_timeout_seconds=(
            arguments.analysis_timeout_seconds
        ),
        stack_manifest=stack_manifest,
    )

    physics = result.physics
    analysis_execution = (
        result.analysis.execution
        if result.analysis is not None
        else None
    )

    lhe_file = (
        physics.primary_lhe_file
        if physics is not None
        else None
    )
    hepmc_file = (
        physics.showered_hepmc_file
        if physics is not None
        else None
    )
    delphes_file = (
        physics.detector_root_file
        if physics is not None
        else None
    )
    html_report = (
        analysis_execution.html_report
        if analysis_execution is not None
        else None
    )
    pdf_report = (
        analysis_execution.pdf_report
        if analysis_execution is not None
        else None
    )
    plot_files = (
        analysis_execution.plot_files
        if analysis_execution is not None
        else ()
    )

    checks = {
        "MadGraph execution": bool(
            result.execution
            and result.execution.success
        ),
        "LHE events": existing_file(lhe_file),
        "Pythia8 HepMC": existing_file(hepmc_file),
        "Delphes ROOT": existing_file(delphes_file),
        "MadAnalysis execution": bool(
            result.analysis
            and result.analysis.success
        ),
        "MadAnalysis HTML": existing_file(html_report),
        "MadAnalysis plots": bool(plot_files),
    }

    print()
    print("=" * 72)
    print("VALIDATION RESULTS")
    print("=" * 72)
    for name, passed in checks.items():
        label = "PASS" if passed else "FAIL"
        print(f"[{label}] {name}")

    print()
    print(f"Agent status:   {result.status.value}")
    print(f"Run ID:         {result.final_record.run_id}")
    print(f"LHE:            {lhe_file}")
    print(f"HepMC:          {hepmc_file}")
    print(f"Delphes ROOT:   {delphes_file}")
    print(f"MA5 HTML:       {html_report}")
    print(f"MA5 PDF:        {pdf_report}")
    print(f"MA5 plot count: {len(plot_files)}")
    print(
        "MA5 input:      managed Delphes ROOT output (reconstructed level)."
    )

    success = result.success and all(checks.values())
    summary = {
        "success": success,
        "status": result.status.value,
        "run_id": result.final_record.run_id,
        "checks": checks,
        "artifacts": {
            "lhe": str(lhe_file) if lhe_file else None,
            "hepmc": str(hepmc_file) if hepmc_file else None,
            "delphes_root": (
                str(delphes_file)
                if delphes_file
                else None
            ),
            "madanalysis_html": (
                str(html_report)
                if html_report
                else None
            ),
            "madanalysis_pdf": (
                str(pdf_report)
                if pdf_report
                else None
            ),
            "madanalysis_plots": [
                str(path)
                for path in plot_files
            ],
        },
    }
    summary_path = output_directory / "validation_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Summary:        {summary_path}")
    print()

    if success:
        print("FULL HEP STACK VALIDATION PASSED")
        return 0

    print("FULL HEP STACK VALIDATION FAILED")
    if result.execution and result.execution.stdout_path:
        print(f"MadGraph log:   {result.execution.stdout_path}")
    if analysis_execution is not None:
        print(f"MA5 stdout:     {analysis_execution.stdout_path}")
        print(f"MA5 stderr:     {analysis_execution.stderr_path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
