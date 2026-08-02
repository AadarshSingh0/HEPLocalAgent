#!/usr/bin/env python3
"""Evaluate the thin semantic planner plus deterministic compiler."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from hep_agent.builders import (
    build_madgraph_workflow_artifact,
)
from hep_agent.models import OllamaClient
from hep_agent.models.semantic_process import (
    SemanticPlanningError,
    compile_semantic_process_workflow,
    plan_semantic_process,
)


ROOT = Path(
    __file__
).resolve().parents[1]

SCENARIO_FILE = (
    ROOT
    / "evaluation"
    / "process_generalization_v1.json"
)

RESULT_ROOT = (
    ROOT
    / "evaluation"
    / "results"
    / "semantic_agent_v1"
)

EXPECTED_SAFE_BLOCKS = {
    "D05",
}


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


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--model",
        default=(
            "qwen3-coder-next:Q4_K_M"
        ),
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

    args = parser.parse_args()

    payload = json.loads(
        SCENARIO_FILE.read_text(
            encoding="utf-8"
        )
    )

    scenarios = [
        scenario
        for scenario
        in payload["scenarios"]
        if scenario["group"] == "decay"
    ]

    output_directory = (
        RESULT_ROOT
        / args.run_label
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=False,
    )

    client = OllamaClient()
    results = []

    for index, scenario in enumerate(
        scenarios,
        start=1,
    ):
        scenario_id = scenario[
            "scenario_id"
        ]

        print()
        print("=" * 90)
        print(
            f"[{index}/{len(scenarios)}] "
            f"{scenario_id}: "
            f"{scenario['description']}"
        )
        print("=" * 90)
        print(scenario["request"])

        status = "failed"
        command = None
        artifact_commands = []
        error_code = None
        error_message = None
        llm_calls = 0

        try:
            semantic = (
                plan_semantic_process(
                    scenario["request"],
                    client=client,
                    model=args.model,
                    timeout_seconds=(
                        args.timeout
                    ),
                )
            )

            llm_calls = 1
            command = (
                semantic.process_command
            )

            workflow = (
                compile_semantic_process_workflow(
                    scenario["request"],
                    command,
                )
            )

            artifact = (
                build_madgraph_workflow_artifact(
                    workflow
                )
            )

            artifact_commands = (
                process_commands(
                    list(
                        artifact.commands
                    )
                )
            )

            status = "ready"

        except SemanticPlanningError as exc:
            error_code = exc.code
            error_message = str(exc)

            if (
                exc.code
                == "ambiguous_channel_request"
            ):
                status = "safe_block"

        except Exception as exc:
            error_code = (
                type(exc).__name__
            )
            error_message = str(exc)

        expected_commands = {
            normalise(item)
            for item in scenario.get(
                "expected_process_commands",
                [],
            )
        }

        actual_commands = {
            normalise(item)
            for item in artifact_commands
        }

        if (
            scenario_id
            in EXPECTED_SAFE_BLOCKS
        ):
            passed = (
                status == "safe_block"
            )

        else:
            passed = bool(
                expected_commands
                and expected_commands
                .intersection(
                    actual_commands
                )
            )

        record = {
            "scenario_id": scenario_id,
            "request": (
                scenario["request"]
            ),
            "model": args.model,
            "status": status,
            "passed": passed,
            "semantic_command": command,
            "artifact_commands": (
                artifact_commands
            ),
            "llm_calls": llm_calls,
            "error_code": error_code,
            "error_message": (
                error_message
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
            "Semantic command:",
            command,
        )
        print(
            "Artifact commands:",
            artifact_commands,
        )
        print("Status:", status)
        print("Pass:", passed)

        if error_message:
            print(
                "Message:",
                error_message,
            )

    passed_count = sum(
        result["passed"]
        for result in results
    )

    summary = {
        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "model": args.model,
        "scenario_count": (
            len(results)
        ),
        "passed": passed_count,
        "pass_rate": (
            passed_count
            / len(results)
            if results
            else 0.0
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
    print(
        "SEMANTIC AGENT EVALUATION FINISHED"
    )
    print("=" * 90)
    print(
        "Passed:",
        passed_count,
        "/",
        len(results),
    )
    print(
        "Output:",
        output_directory,
    )


if __name__ == "__main__":
    main()
