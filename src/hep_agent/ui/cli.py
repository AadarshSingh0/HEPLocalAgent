"""Command-line interface for the local HEP agent."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from hep_agent.models import (
    OllamaClient,
    load_agent_profiles,
)
from hep_agent.orchestration import (
    EndToEndResult,
    PreExecutionResult,
    resolve_terminal_approval,
    run_end_to_end,
)


DEFAULT_PROJECT_ROOT = (
    Path(__file__).resolve().parents[3]
)


def combine_request_parts(parts: Sequence[str]) -> str:
    """Combine quoted or unquoted command-line request words."""

    request = " ".join(part.strip() for part in parts).strip()

    if not request:
        raise ValueError("The user request cannot be empty.")

    return request


def resolve_project_path(
    project_root: str | Path,
    path: str | Path,
) -> Path:
    """Resolve a path relative to the project root."""

    candidate = Path(path).expanduser()

    if candidate.is_absolute():
        return candidate.resolve()

    return (
        Path(project_root).expanduser().resolve()
        / candidate
    ).resolve()


def load_json_object(path: str | Path) -> dict:
    """Load a JSON configuration object."""

    config_path = Path(path)

    if not config_path.is_file():
        raise FileNotFoundError(
            f"Configuration file does not exist: {config_path}"
        )

    payload = json.loads(
        config_path.read_text(encoding="utf-8")
    )

    if not isinstance(payload, dict):
        raise ValueError(
            f"Configuration must contain a JSON object: "
            f"{config_path}"
        )

    return payload


def print_preexecution_summary(
    result: PreExecutionResult,
) -> None:
    """Display the interpreted workflow before approval."""

    print()
    print("=== INTERPRETED WORKFLOW ===")
    print("Pre-execution status:", result.status.value)
    print("LLM calls:", result.llm_call_count)
    print("Repair attempts:", result.repair_attempts)
    print("Fallback used:", result.fallback_used)

    if result.failure_category is not None:
        print(
            "Failure category:",
            result.failure_category.value,
        )

    if result.failure_message:
        print("Failure message:", result.failure_message)

    if result.workflow is None:
        return

    workflow = result.workflow

    print("Model:", workflow.model.name)

    beams = " ".join(
        beam.particle
        for beam in workflow.collider.beams
    )
    energy = workflow.collider.energy

    print(
        "Collider:",
        beams,
        "at",
        f"{energy.value_gev:g}",
        "GeV",
        f"({energy.meaning.value})",
    )

    print("Events:", workflow.run.nevents)
    print(
        "Pipeline:",
        f"MG5={workflow.pipeline.madgraph},",
        f"Pythia8={workflow.pipeline.pythia8},",
        f"Delphes={workflow.pipeline.delphes},",
        f"MadAnalysis={workflow.pipeline.madanalysis}",
    )

    if result.corrections:
        print()
        print("Deterministic corrections:")

        for correction in result.corrections:
            print(
                f"- {correction.path}: "
                f"{correction.previous_value!r} "
                f"→ {correction.corrected_value!r}"
            )
            print(f"  {correction.reason}")
    else:
        print("Deterministic corrections: none")

    if result.artifact is not None:
        print()
        print("=== VALIDATED MG5 WORKFLOW ===")
        print(result.artifact.text)


def print_final_summary(
    result: EndToEndResult,
    *,
    records_directory: Path,
) -> None:
    """Display the final execution and physics summary."""

    record = result.final_record

    print()
    print("=== FINAL AGENT RESULT ===")
    print("Status:", result.status.value)
    print("Success:", result.success)
    print("Run ID:", record.run_id)
    print("LLM calls:", record.llm_call_count)
    print("Repair attempts:", record.repair_attempts)
    print("Fallback used:", record.fallback_used)
    print(
        "Corrections applied:",
        record.corrections_applied,
    )

    print()
    print("=== EXECUTION ===")
    print("Started:", record.execution_started)
    print("Success:", record.execution_success)
    print("Return code:", record.execution_returncode)

    if record.execution_wall_time_seconds is not None:
        print(
            "MG5 wall time:",
            round(
                record.execution_wall_time_seconds,
                2,
            ),
            "seconds",
        )

    if record.end_to_end_wall_time_seconds is not None:
        print(
            "End-to-end wall time:",
            round(
                record.end_to_end_wall_time_seconds,
                2,
            ),
            "seconds",
        )

    if record.execution_failure_category:
        print(
            "Execution failure:",
            record.execution_failure_category,
        )

    print()
    print("=== PHYSICS RESULT ===")
    print(
        "Physics summary found:",
        record.physics_summary_found,
    )

    if record.cross_section_pb is not None:
        print(
            "Cross section:",
            record.cross_section_pb,
            "+-",
            record.cross_section_uncertainty_pb,
            "pb",
        )

    print(
        "Generated events:",
        record.generated_event_count,
    )
    print("Parton-level LHE:", record.primary_lhe_file)
    print(
        "Showered HepMC:",
        record.showered_hepmc_file,
    )
    print(
        "Detector-level ROOT:",
        record.detector_root_file,
    )
    print(
        "Missing requested outputs:",
        (
            ", ".join(
                record.missing_requested_outputs
            )
            if record.missing_requested_outputs
            else "None"
        ),
    )

    print("Warnings:")

    if record.execution_warnings:
        for warning in record.execution_warnings:
            print("-", warning)
    else:
        print("None")

    print()
    print("=== MADANALYSIS ===")
    print("Requested:", record.analysis_requested)
    print("Started:", record.analysis_started)
    print("Success:", record.analysis_success)
    print("Level:", record.analysis_level)
    print("Input file:", record.analysis_input_file)

    if record.analysis_wall_time_seconds is not None:
        print(
            "MA5 wall time:",
            round(
                record.analysis_wall_time_seconds,
                2,
            ),
            "seconds",
        )

    if record.analysis_failure_category:
        print(
            "Failure category:",
            record.analysis_failure_category,
        )
        print(
            "Failure message:",
            record.analysis_failure_message,
        )

    print("HTML report:", record.analysis_html_report)
    print("PDF report:", record.analysis_pdf_report)
    print(
        "Plot count:",
        len(record.analysis_plot_files),
    )

    print()
    print("=== SAVED OUTPUTS ===")
    print(
        "Execution directory:",
        record.execution_directory,
    )
    print("Command file:", record.command_script_path)
    print("Stdout:", record.stdout_path)
    print("Stderr:", record.stderr_path)
    print(
        "JSON record:",
        records_directory / f"{record.run_id}.json",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the hep-agent command parser."""

    parser = argparse.ArgumentParser(
        prog="hep-agent",
        description=(
            "Plan, validate, approve, and execute local "
            "high-energy-physics workflows."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Run a natural-language collider request.",
    )

    run_parser.add_argument(
        "request",
        nargs="+",
        help=(
            "Natural-language request. It may be quoted or "
            "provided as several command-line words."
        ),
    )
    run_parser.add_argument(
        "--profile",
        default="qwen_primary",
        help="Agent profile name. Default: qwen_primary",
    )
    run_parser.add_argument(
        "--project-root",
        default=str(DEFAULT_PROJECT_ROOT),
        help="Local HEP-agent project root.",
    )
    run_parser.add_argument(
        "--profiles-config",
        default="configs/agent_profiles.json",
        help="Agent-profile configuration path.",
    )
    run_parser.add_argument(
        "--local-paths",
        default="configs/local_paths.json",
        help="Machine-local executable configuration.",
    )
    run_parser.add_argument(
        "--records-dir",
        default="results/runs",
        help="Directory for JSON run records.",
    )
    run_parser.add_argument(
        "--executions-dir",
        default="results/executions",
        help="Directory for external execution outputs.",
    )
    run_parser.add_argument(
        "--analyses-dir",
        default="results/analyses",
        help="Directory for MadAnalysis outputs.",
    )
    run_parser.add_argument(
        "--ollama-host",
        default=None,
        help=(
            "Optional Ollama host override, for example "
            "http://OTHER-COMPUTER:11434"
        ),
    )

    return parser


def run_command(args: argparse.Namespace) -> int:
    """Execute the `hep-agent run` command."""

    request = combine_request_parts(args.request)

    project_root = Path(
        args.project_root
    ).expanduser().resolve()

    profiles_path = resolve_project_path(
        project_root,
        args.profiles_config,
    )
    local_paths_path = resolve_project_path(
        project_root,
        args.local_paths,
    )
    records_directory = resolve_project_path(
        project_root,
        args.records_dir,
    )
    executions_directory = resolve_project_path(
        project_root,
        args.executions_dir,
    )
    analyses_directory = resolve_project_path(
        project_root,
        args.analyses_dir,
    )

    if args.ollama_host:
        os.environ["OLLAMA_HOST"] = args.ollama_host

    profiles = load_agent_profiles(profiles_path)

    if args.profile not in profiles:
        available = ", ".join(sorted(profiles))
        raise ValueError(
            f"Unknown agent profile {args.profile!r}. "
            f"Available profiles: {available}"
        )

    profile = profiles[args.profile]

    local_paths = load_json_object(
        local_paths_path
    )

    mg5_executable = local_paths.get(
        "mg5_executable"
    )

    if not mg5_executable:
        raise ValueError(
            "configs/local_paths.json does not define "
            "'mg5_executable'."
        )

    madanalysis_executable = local_paths.get(
        "madanalysis5_executable"
    )

    print("=== LOCAL HEP AGENT ===")
    print("Request:", request)
    print("Profile:", args.profile)
    print(
        "Primary model:",
        profile.primary_model,
    )
    print(
        "Ollama host:",
        os.environ.get(
            "OLLAMA_HOST",
            "http://localhost:11434",
        ),
    )
    print("MadGraph:", mg5_executable)
    print(
        "MadAnalysis5:",
        madanalysis_executable or "not configured",
    )

    result = run_end_to_end(
        request,
        client=OllamaClient(),
        profile_name=args.profile,
        profile=profile,
        mg5_executable=mg5_executable,
        madanalysis_executable=(
            madanalysis_executable
        ),
        approval_resolver=resolve_terminal_approval,
        preexecution_observer=(
            print_preexecution_summary
        ),
        records_directory=records_directory,
        executions_directory=executions_directory,
        analyses_directory=analyses_directory,
        project_root=project_root,
    )

    print_final_summary(
        result,
        records_directory=records_directory,
    )

    if result.success:
        return 0

    status_codes = {
        "cancelled": 3,
        "blocked": 4,
        "preexecution_failed": 5,
        "execution_failed": 6,
        "analysis_failed": 7,
    }

    return status_codes.get(
        result.status.value,
        1,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "run":
            return run_command(args)

        parser.error(
            f"Unsupported command: {args.command}"
        )

    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        ValueError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
