#!/usr/bin/env python3
"""Test pure natural-language-to-MadGraph process interpretation.

This diagnostic deliberately avoids WorkflowIntent, Pydantic schema
validation, grounding correction, repair, and artifact construction.

It tests only:

    user request -> one MadGraph generate command
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hep_agent.models import OllamaClient


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SCENARIOS = (
    ROOT
    / "evaluation"
    / "process_generalization_v1.json"
)

RESULTS_ROOT = (
    ROOT
    / "evaluation"
    / "results"
    / "process_semantic_comparison"
)


SYSTEM_PROMPT = """You translate collider-simulation requests into MadGraph process syntax.

Return exactly one line beginning with:

generate

Do not return JSON.
Do not explain.
Do not add coupling-order restrictions unless the user explicitly requests them.
Do not invent decay chains.
Preserve explicitly requested decays and intermediate channels.

Examples:

Request:
Produce an electron pair in proton-proton collisions.

Answer:
generate p p > e+ e-

Request:
Produce a Z boson and decay it to an electron and a positron.

Answer:
generate p p > z, z > e+ e-

Request:
Restrict electron-pair production to the Z channel.

Answer:
generate p p > z > e+ e-
"""


def normalise(command: str) -> str:
    return " ".join(
        command.strip().lower().split()
    )


def extract_generate_command(
    content: str,
) -> str | None:
    """Extract the first standalone MadGraph generate command."""

    cleaned = content.replace(
        "```madgraph",
        "",
    ).replace(
        "```text",
        "",
    ).replace(
        "```",
        "",
    )

    for line in cleaned.splitlines():
        stripped = line.strip()

        if stripped.lower().startswith(
            "generate "
        ):
            return " ".join(
                stripped.split()
            )

    match = re.search(
        r"\bgenerate\s+[^\n\r]+",
        cleaned,
        re.IGNORECASE,
    )

    if match is None:
        return None

    return " ".join(
        match.group(0).strip().split()
    )


def exact_match(
    actual: str | None,
    expected_commands: list[str],
) -> bool:
    if actual is None:
        return False

    expected = {
        normalise(command)
        for command in expected_commands
    }

    return normalise(actual) in expected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--model",
        required=True,
    )

    parser.add_argument(
        "--groups",
        nargs="+",
        default=["decay"],
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
        default=600,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    payload = json.loads(
        args.scenario_file.read_text(
            encoding="utf-8"
        )
    )

    groups = set(args.groups)

    scenarios = [
        scenario
        for scenario in payload["scenarios"]
        if scenario["group"] in groups
    ]

    if args.scenario_ids:
        selected = set(args.scenario_ids)

        scenarios = [
            scenario
            for scenario in scenarios
            if scenario["scenario_id"]
            in selected
        ]

    output_directory = (
        RESULTS_ROOT
        / args.run_label
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=False,
    )

    client = OllamaClient()
    results: list[dict[str, Any]] = []

    for index, scenario in enumerate(
        scenarios,
        start=1,
    ):
        print()
        print("=" * 90)
        print(
            f"[{index}/{len(scenarios)}] "
            f"{scenario['scenario_id']}: "
            f"{scenario['description']}"
        )
        print("=" * 90)
        print(scenario["request"])

        started = time.perf_counter()

        response_content = None
        command = None
        error = None
        duration = None

        try:
            response = client.chat(
                model=args.model,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": scenario["request"],
                    },
                ],
                response_schema=None,
                temperature=0.0,
                num_predict=300,
                timeout_seconds=args.timeout,
            )

            response_content = response.content
            duration = (
                response.total_duration_seconds
            )
            command = extract_generate_command(
                response.content
            )

        except Exception as exc:
            error = (
                f"{type(exc).__name__}: {exc}"
            )

        wall_time = (
            time.perf_counter()
            - started
        )

        passed = exact_match(
            command,
            scenario.get(
                "expected_process_commands",
                [],
            ),
        )

        result = {
            "scenario_id": scenario[
                "scenario_id"
            ],
            "description": scenario[
                "description"
            ],
            "request": scenario["request"],
            "model": args.model,
            "expected_process_commands": (
                scenario.get(
                    "expected_process_commands",
                    [],
                )
            ),
            "actual_process_command": command,
            "exact": passed,
            "raw_content": response_content,
            "error": error,
            "model_duration_seconds": duration,
            "wall_time_seconds": wall_time,
        }

        results.append(result)

        (
            output_directory
            / f"{scenario['scenario_id']}.json"
        ).write_text(
            json.dumps(
                result,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        print("Command:", command)
        print("Exact:", passed)

        if error:
            print("Error:", error)

        if (
            not passed
            and response_content
        ):
            print(
                "Raw response:",
                repr(response_content),
            )

    exact_count = sum(
        result["exact"]
        for result in results
    )

    summary = {
        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "model": args.model,
        "scenario_count": len(results),
        "exact_count": exact_count,
        "exact_rate": (
            exact_count / len(results)
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
    print("SEMANTIC PROCESS COMPARISON FINISHED")
    print("=" * 90)
    print("Model:", args.model)
    print(
        "Exact:",
        exact_count,
        "/",
        len(results),
    )
    print("Output:", output_directory)


if __name__ == "__main__":
    main()
