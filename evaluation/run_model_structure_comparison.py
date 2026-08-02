#!/usr/bin/env python3
"""Compare raw planner ability with final structured-agent output."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hep_agent.builders import (
    build_madgraph_workflow_artifact,
)
from hep_agent.models import (
    OllamaClient,
    load_agent_profiles,
    plan_workflow,
)
from hep_agent.orchestration.preexecution import (
    run_preexecution_loop,
)


ROOT = Path(
    __file__
).resolve().parents[1]

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
    / "model_structure_comparison"
)


def normalise(
    command: str,
) -> str:
    return " ".join(
        command.lower().split()
    )


def process_commands(
    commands: list[str],
) -> list[str]:
    return [
        command
        for command in commands
        if (
            command.startswith(
                "generate "
            )
            or command.startswith(
                "add process "
            )
        )
    ]


def exact_match(
    scenario: dict[str, Any],
    commands: list[str],
) -> bool:
    expected = {
        normalise(command)
        for command in scenario.get(
            "expected_process_commands",
            [],
        )
    }

    actual = {
        normalise(command)
        for command in process_commands(
            commands
        )
    }

    return bool(
        expected
        and expected.intersection(actual)
    )


def build_commands(
    workflow: Any,
) -> tuple[
    list[str],
    str | None,
]:
    try:
        artifact = (
            build_madgraph_workflow_artifact(
                workflow
            )
        )

        return (
            list(artifact.commands),
            None,
        )

    except Exception as exc:
        return (
            [],
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )


def make_client() -> OllamaClient:
    """Return the configured Ollama client."""

    return OllamaClient()


def copy_profile_with_model(
    base_profile: Any,
    *,
    model: str,
    timeout_seconds: int,
) -> Any:
    """Copy an AgentProfile without assuming it is a dataclass."""

    updates = {
        "primary_model": model,
        "fallback_model": None,
        "primary_timeout_seconds": timeout_seconds,
        "fallback_timeout_seconds": None,
    }

    if hasattr(
        base_profile,
        "model_copy",
    ):
        return base_profile.model_copy(
            update=updates
        )

    if isinstance(
        base_profile,
        dict,
    ):
        copied = dict(base_profile)
        copied.update(updates)
        return copied

    raise TypeError(
        "Unsupported AgentProfile type: "
        f"{type(base_profile).__name__}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--model",
        required=True,
    )

    parser.add_argument(
        "--base-profile",
        default="qwen_primary",
    )

    parser.add_argument(
        "--groups",
        nargs="+",
        default=[
            "decay",
        ],
    )

    parser.add_argument(
        "--scenario-ids",
        nargs="*",
        default=None,
    )

    parser.add_argument(
        "--scenario-file",
        type=Path,
        default=DEFAULT_SCENARIOS,
    )

    parser.add_argument(
        "--run-label",
        required=True,
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    scenario_payload = json.loads(
        args.scenario_file.read_text(
            encoding="utf-8"
        )
    )

    selected_groups = set(
        args.groups
    )

    scenarios = [
        scenario
        for scenario
        in scenario_payload[
            "scenarios"
        ]
        if scenario["group"]
        in selected_groups
    ]

    if args.scenario_ids:
        selected_ids = set(
            args.scenario_ids
        )

        scenarios = [
            scenario
            for scenario in scenarios
            if scenario[
                "scenario_id"
            ] in selected_ids
        ]

    profiles = load_agent_profiles(
        DEFAULT_PROFILES
    )

    if (
        args.base_profile
        not in profiles
    ):
        raise SystemExit(
            (
                "Unknown base profile: "
                f"{args.base_profile}"
            )
        )

    base_profile = profiles[
        args.base_profile
    ]

    comparison_profile = copy_profile_with_model(
        base_profile,
        model=args.model,
        timeout_seconds=args.timeout,
    )

    output_directory = (
        RESULTS_ROOT
        / args.run_label
    )

    output_directory.mkdir(
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

        request = scenario[
            "request"
        ]

        print()
        print("=" * 90)
        print(
            f"[{index}/{len(scenarios)}] "
            f"{scenario_id}: "
            f"{scenario['description']}"
        )
        print("=" * 90)
        print(request)

        client = make_client()

        raw_started = (
            time.perf_counter()
        )

        raw_workflow = None
        raw_content = None
        raw_error = None
        raw_commands: list[str] = []
        raw_builder_error = None
        raw_duration = None
        raw_prompt_tokens = None
        raw_completion_tokens = None

        try:
            raw_result = plan_workflow(
                request,
                client=client,
                model=args.model,
                timeout_seconds=(
                    args.timeout
                ),
            )

            raw_workflow = (
                raw_result.workflow
            )

            raw_content = (
                raw_result.raw_content
            )

            raw_duration = (
                raw_result
                .model_response
                .total_duration_seconds
            )

            raw_prompt_tokens = (
                raw_result
                .model_response
                .prompt_eval_count
            )

            raw_completion_tokens = (
                raw_result
                .model_response
                .eval_count
            )

            (
                raw_commands,
                raw_builder_error,
            ) = build_commands(
                raw_workflow
            )

        except Exception as exc:
            raw_error = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )

        raw_wall_time = (
            time.perf_counter()
            - raw_started
        )

        final_started = (
            time.perf_counter()
        )

        final_result = (
            run_preexecution_loop(
                request,
                client=client,
                profile=(
                    comparison_profile
                ),
            )
        )

        final_wall_time = (
            time.perf_counter()
            - final_started
        )

        final_commands = (
            list(
                final_result
                .artifact
                .commands
            )
            if final_result.artifact
            is not None
            else []
        )

        raw_exact = exact_match(
            scenario,
            raw_commands,
        )

        final_exact = exact_match(
            scenario,
            final_commands,
        )

        if raw_exact and final_exact:
            interpretation = (
                "model_and_structure_correct"
            )

        elif (
            raw_exact
            and not final_exact
        ):
            interpretation = (
                "structure_regression"
            )

        elif (
            not raw_exact
            and final_exact
        ):
            interpretation = (
                "structure_recovery"
            )

        else:
            interpretation = (
                "model_and_final_incorrect"
            )

        record = {
            "scenario_id": (
                scenario_id
            ),
            "description": (
                scenario[
                    "description"
                ]
            ),
            "request": request,
            "provider": "ollama",
            "model": args.model,
            "expected_process_commands": (
                scenario.get(
                    "expected_process_commands",
                    [],
                )
            ),
            "raw_planner": {
                "exact": raw_exact,
                "commands": (
                    process_commands(
                        raw_commands
                    )
                ),
                "all_commands": (
                    raw_commands
                ),
                "workflow": (
                    raw_workflow
                    .model_dump(
                        mode="json"
                    )
                    if raw_workflow
                    is not None
                    else None
                ),
                "raw_content": (
                    raw_content
                ),
                "planner_error": (
                    raw_error
                ),
                "builder_error": (
                    raw_builder_error
                ),
                "model_duration_seconds": (
                    raw_duration
                ),
                "wall_time_seconds": (
                    raw_wall_time
                ),
                "prompt_tokens": (
                    raw_prompt_tokens
                ),
                "completion_tokens": (
                    raw_completion_tokens
                ),
            },
            "final_agent": {
                "exact": final_exact,
                "ready": (
                    final_result.is_ready
                ),
                "status": (
                    final_result
                    .status
                    .value
                ),
                "commands": (
                    process_commands(
                        final_commands
                    )
                ),
                "all_commands": (
                    final_commands
                ),
                "workflow": (
                    final_result
                    .workflow
                    .model_dump(
                        mode="json"
                    )
                    if final_result.workflow
                    is not None
                    else None
                ),
                "failure_category": (
                    final_result
                    .failure_category
                    .value
                    if final_result
                    .failure_category
                    is not None
                    else None
                ),
                "failure_message": (
                    final_result
                    .failure_message
                ),
                "llm_call_count": (
                    final_result
                    .llm_call_count
                ),
                "repair_attempts": (
                    final_result
                    .repair_attempts
                ),
                "wall_time_seconds": (
                    final_wall_time
                ),
            },
            "interpretation": (
                interpretation
            ),
        }

        results.append(record)

        (
            output_directory
            / f"{scenario_id}.json"
        ).write_text(
            json.dumps(
                record,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        print(
            "Raw planner:",
            process_commands(
                raw_commands
            ),
        )

        print(
            "Raw exact:",
            raw_exact,
        )

        print(
            "Final agent:",
            process_commands(
                final_commands
            ),
        )

        print(
            "Final exact:",
            final_exact,
        )

        print(
            "Interpretation:",
            interpretation,
        )

    summary = {
        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "provider": "ollama",
        "model": args.model,
        "scenario_count": (
            len(results)
        ),
        "raw_exact_count": sum(
            result[
                "raw_planner"
            ]["exact"]
            for result in results
        ),
        "final_exact_count": sum(
            result[
                "final_agent"
            ]["exact"]
            for result in results
        ),
        "structure_regressions": sum(
            result[
                "interpretation"
            ]
            == "structure_regression"
            for result in results
        ),
        "structure_recoveries": sum(
            result[
                "interpretation"
            ]
            == "structure_recovery"
            for result in results
        ),
        "results": results,
    }

    (
        output_directory
        / "summary.json"
    ).write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 90)
    print("COMPARISON FINISHED")
    print("=" * 90)
    print(
        "Output:",
        output_directory,
    )
    print(
        "Raw planner exact:",
        summary[
            "raw_exact_count"
        ],
        "/",
        summary[
            "scenario_count"
        ],
    )
    print(
        "Final agent exact:",
        summary[
            "final_exact_count"
        ],
        "/",
        summary[
            "scenario_count"
        ],
    )
    print(
        "Structure regressions:",
        summary[
            "structure_regressions"
        ],
    )
    print(
        "Structure recoveries:",
        summary[
            "structure_recoveries"
        ],
    )


if __name__ == "__main__":
    main()
