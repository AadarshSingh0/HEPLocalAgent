#!/usr/bin/env python3
"""Run the frozen process-generalization suite without HEP execution."""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hep_agent.models import (
    OllamaClient,
    load_agent_profiles,
)
from hep_agent.orchestration.preexecution import (
    run_preexecution_loop,
)
from hep_agent.validation.workflow_request import (
    validate_workflow_request_minimum,
)


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SCENARIOS = (
    ROOT
    / "evaluation"
    / "process_generalization_v1.json"
)

DEFAULT_PROFILES = (
    ROOT
    / "configs"
    / "agent_profiles.json"
)

RESULTS_ROOT = (
    ROOT
    / "evaluation"
    / "results"
    / "process_generalization_v1"
)


def normalise_command(command: str) -> str:
    return " ".join(
        command.lower().split()
    )


def particle_names(
    final_particles: list[Any],
) -> list[str]:
    names: list[str] = []

    for item in final_particles:
        if isinstance(item, dict):
            names.append(
                str(item.get("particle"))
            )
        else:
            names.append(
                str(
                    getattr(
                        item,
                        "particle",
                        item,
                    )
                )
            )

    return names


def issue_codes(report: Any) -> list[str]:
    if report is None:
        return []

    return [
        issue.code
        for issue in report.errors
    ]


def evaluate_ready_scenario(
    scenario: dict[str, Any],
    *,
    ready: bool,
    workflow: dict[str, Any] | None,
    commands: list[str],
) -> list[str]:
    failed: list[str] = []

    if not ready:
        return ["ready_state"]

    if workflow is None:
        return ["workflow_missing"]

    process_commands = [
        command
        for command in commands
        if (
            command.startswith("generate ")
            or command.startswith("add process ")
        )
    ]

    expected_commands = {
        normalise_command(command)
        for command
        in scenario.get(
            "expected_process_commands",
            [],
        )
    }

    actual_commands = {
        normalise_command(command)
        for command in process_commands
    }

    if len(process_commands) != 1:
        failed.append(
            "process_command_count"
        )

    if (
        expected_commands
        and not (
            expected_commands
            & actual_commands
        )
    ):
        failed.append(
            "exact_process_command"
        )

    processes = workflow.get(
        "processes",
        [],
    )

    if len(processes) != 1:
        failed.append(
            "workflow_process_count"
        )
        return failed

    process = processes[0]

    expected_incoming = scenario.get(
        "expected_incoming"
    )

    if (
        expected_incoming is not None
        and process.get(
            "incoming_particles"
        )
        != expected_incoming
    ):
        failed.append(
            "incoming_particles"
        )

    expected_final = scenario.get(
        "expected_final"
    )

    actual_final = particle_names(
        process.get(
            "final_particles",
            [],
        )
    )

    if (
        expected_final is not None
        and actual_final != expected_final
    ):
        failed.append(
            "final_particles"
        )

    expected_intermediates = (
        scenario.get(
            "expected_required_intermediates"
        )
    )

    actual_intermediates = [
        str(item).lower()
        for item in process.get(
            "required_intermediates",
            [],
        )
    ]

    if expected_intermediates is not None:
        expected_intermediates = [
            str(item).lower()
            for item in expected_intermediates
        ]

        if (
            actual_intermediates
            != expected_intermediates
        ):
            failed.append(
                "required_intermediates"
            )

    if process.get(
        "excluded_particles",
        [],
    ):
        failed.append(
            "invented_excluded_particles"
        )

    if process.get(
        "coupling_orders",
        {},
    ):
        failed.append(
            "invented_coupling_orders"
        )

    expected_energy = scenario.get(
        "expected_energy_gev"
    )

    actual_energy = (
        workflow.get(
            "collider",
            {},
        )
        .get(
            "energy",
            {},
        )
        .get(
            "value_gev"
        )
    )

    if (
        expected_energy is not None
        and (
            actual_energy is None
            or abs(
                float(actual_energy)
                - float(expected_energy)
            )
            > 1.0e-9
        )
    ):
        failed.append(
            "collider_energy"
        )

    expected_nevents = scenario.get(
        "expected_nevents"
    )

    actual_nevents = (
        workflow.get(
            "run",
            {},
        )
        .get(
            "nevents"
        )
    )

    if (
        expected_nevents is not None
        and actual_nevents
        != expected_nevents
    ):
        failed.append(
            "event_count"
        )

    pipeline = workflow.get(
        "pipeline",
        {},
    )

    if pipeline.get("madgraph") is not True:
        failed.append(
            "madgraph_disabled"
        )

    for stage in (
        "pythia8",
        "delphes",
        "madanalysis",
    ):
        if pipeline.get(stage) is not False:
            failed.append(
                f"invented_{stage}"
            )

    return failed


def run_scenario(
    scenario: dict[str, Any],
    *,
    client: OllamaClient,
    profile: Any,
) -> dict[str, Any]:
    started = time.perf_counter()

    minimum = (
        validate_workflow_request_minimum(
            scenario["request"]
        )
    )

    result = None

    if minimum.is_valid:
        try:
            result = run_preexecution_loop(
                scenario["request"],
                client=client,
                profile=profile,
            )
            crash = None
        except Exception as exc:
            crash = (
                f"{type(exc).__name__}: {exc}"
            )
    else:
        crash = None

    wall_time = (
        time.perf_counter()
        - started
    )

    if result is None:
        ready = False
        status = (
            "blocked_minimum_request"
            if not minimum.is_valid
            else "crashed"
        )
        llm_calls = 0
        repairs = 0
        fallback = False
        failure_category = (
            "incomplete_request"
            if not minimum.is_valid
            else "runner_crash"
        )
        failure_message = (
            "; ".join(
                issue.message
                for issue
                in minimum.errors
            )
            if not minimum.is_valid
            else crash
        )
        workflow = None
        commands: list[str] = []
        model_calls: list[dict[str, Any]] = []
        grounding_codes: list[str] = []
        artifact_codes: list[str] = []
    else:
        ready = result.is_ready
        status = result.status.value
        llm_calls = result.llm_call_count
        repairs = result.repair_attempts
        fallback = result.fallback_used

        failure_category = (
            result.failure_category.value
            if result.failure_category
            is not None
            else None
        )

        failure_message = (
            result.failure_message
        )

        workflow = (
            result.workflow.model_dump(
                mode="json"
            )
            if result.workflow
            is not None
            else None
        )

        commands = (
            list(
                result.artifact.commands
            )
            if result.artifact
            is not None
            else []
        )

        model_calls = [
            {
                "role": call.role,
                "model": call.model,
                "duration_seconds": (
                    call.duration_seconds
                ),
            }
            for call in result.model_calls
        ]

        grounding_codes = issue_codes(
            result.grounding_report
        )
        artifact_codes = issue_codes(
            result.artifact_report
        )

    expectation = scenario[
        "expectation"
    ]

    if expectation == "ready_exact":
        failed_checks = (
            evaluate_ready_scenario(
                scenario,
                ready=ready,
                workflow=workflow,
                commands=commands,
            )
        )

    elif expectation == "not_ready":
        failed_checks = []

        if ready:
            failed_checks.append(
                "unsafe_ready_state"
            )

        if (
            scenario.get(
                "expected_zero_llm",
                False,
            )
            and llm_calls != 0
        ):
            failed_checks.append(
                "unexpected_llm_call"
            )

    else:
        failed_checks = [
            "unknown_expectation"
        ]

    evaluation_pass = (
        not failed_checks
        and crash is None
    )

    process_commands = [
        command
        for command in commands
        if (
            command.startswith("generate ")
            or command.startswith("add process ")
        )
    ]

    return {
        "scenario_id": scenario[
            "scenario_id"
        ],
        "group": scenario["group"],
        "description": scenario[
            "description"
        ],
        "request": scenario["request"],
        "expectation": expectation,
        "evaluation_pass": (
            evaluation_pass
        ),
        "ready": ready,
        "status": status,
        "llm_call_count": llm_calls,
        "repair_attempts": repairs,
        "fallback_used": fallback,
        "wall_time_seconds": wall_time,
        "failure_category": (
            failure_category
        ),
        "failure_message": (
            failure_message
        ),
        "minimum_request_errors": (
            issue_codes(minimum)
        ),
        "grounding_errors": (
            grounding_codes
        ),
        "artifact_errors": (
            artifact_codes
        ),
        "failed_checks": failed_checks,
        "process_commands": (
            process_commands
        ),
        "artifact_commands": commands,
        "workflow": workflow,
        "model_calls": model_calls,
        "crash": crash,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--profile",
        default="qwen_primary",
    )
    parser.add_argument(
        "--groups",
        nargs="+",
        choices=[
            "core",
            "decay",
            "safety",
        ],
        default=[
            "core",
            "decay",
            "safety",
        ],
    )
    parser.add_argument(
        "--scenario-ids",
        nargs="*",
        default=None,
    )
    parser.add_argument(
        "--run-label",
        required=True,
    )
    parser.add_argument(
        "--sleep-between",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--scenario-file",
        type=Path,
        default=DEFAULT_SCENARIOS,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    payload = json.loads(
        args.scenario_file.read_text(
            encoding="utf-8"
        )
    )

    scenarios = [
        scenario
        for scenario
        in payload["scenarios"]
        if scenario["group"]
        in set(args.groups)
    ]

    if args.scenario_ids:
        selected = set(
            args.scenario_ids
        )

        scenarios = [
            scenario
            for scenario in scenarios
            if scenario["scenario_id"]
            in selected
        ]

    profiles = load_agent_profiles(
        DEFAULT_PROFILES
    )

    if args.profile not in profiles:
        raise SystemExit(
            f"Unknown profile: {args.profile}"
        )

    profile = profiles[args.profile]
    client = OllamaClient()

    output = (
        RESULTS_ROOT
        / args.run_label
    )

    trials_directory = (
        output
        / "trials"
    )

    trials_directory.mkdir(
        parents=True,
        exist_ok=False,
    )

    results: list[
        dict[str, Any]
    ] = []

    for index, scenario in enumerate(
        scenarios,
        start=1,
    ):
        scenario_id = scenario[
            "scenario_id"
        ]

        print()
        print("=" * 80)
        print(
            f"[{index}/{len(scenarios)}] "
            f"{scenario_id}: "
            f"{scenario['description']}"
        )
        print("=" * 80)
        print(scenario["request"])

        trial = run_scenario(
            scenario,
            client=client,
            profile=profile,
        )

        results.append(trial)

        trial_path = (
            trials_directory
            / (
                f"{args.profile}__"
                f"{scenario_id}.json"
            )
        )

        trial_path.write_text(
            json.dumps(
                trial,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        print(
            "Evaluation pass:",
            trial[
                "evaluation_pass"
            ],
        )
        print(
            "Status:",
            trial["status"],
        )
        print(
            "Ready:",
            trial["ready"],
        )
        print(
            "LLM calls:",
            trial[
                "llm_call_count"
            ],
        )
        print(
            "Repairs:",
            trial[
                "repair_attempts"
            ],
        )
        print(
            "Process commands:",
            trial[
                "process_commands"
            ],
        )
        print(
            "Failed checks:",
            (
                trial["failed_checks"]
                or "none"
            ),
        )

        if (
            args.sleep_between > 0
            and index < len(scenarios)
        ):
            time.sleep(
                args.sleep_between
            )

    passed = sum(
        result["evaluation_pass"]
        for result in results
    )

    crashes = sum(
        result["crash"] is not None
        for result in results
    )

    summary = {
        "suite_name": payload[
            "suite_name"
        ],
        "suite_version": payload[
            "suite_version"
        ],
        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "profile": args.profile,
        "groups": args.groups,
        "scenario_count": len(results),
        "passed": passed,
        "failed": (
            len(results) - passed
        ),
        "pass_rate": (
            passed / len(results)
            if results
            else 0.0
        ),
        "crashes": crashes,
        "results": results,
    }

    (
        output
        / "summary.json"
    ).write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    csv_fields = [
        "scenario_id",
        "group",
        "evaluation_pass",
        "ready",
        "status",
        "llm_call_count",
        "repair_attempts",
        "fallback_used",
        "wall_time_seconds",
        "process_commands",
        "failed_checks",
        "failure_category",
    ]

    with (
        output
        / "summary.csv"
    ).open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=csv_fields,
        )
        writer.writeheader()

        for result in results:
            row = {
                field: result.get(field)
                for field in csv_fields
            }

            row[
                "process_commands"
            ] = json.dumps(
                row[
                    "process_commands"
                ]
            )

            row[
                "failed_checks"
            ] = json.dumps(
                row[
                    "failed_checks"
                ]
            )

            writer.writerow(row)

    print()
    print("=" * 80)
    print(
        "PROCESS GENERALIZATION "
        "EVALUATION FINISHED"
    )
    print("=" * 80)
    print("Output:", output)
    print(
        f"Passed: {passed}/"
        f"{len(results)}"
    )
    print(
        "Pass rate:",
        summary["pass_rate"],
    )
    print("Crashes:", crashes)


if __name__ == "__main__":
    main()
