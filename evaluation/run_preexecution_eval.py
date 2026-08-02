#!/usr/bin/env python3
"""Run the frozen pre-execution generalization evaluation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from hep_agent.evaluation import (
    evaluate_prepared_scenario,
)
from hep_agent.models import (
    OllamaClient,
    load_agent_profiles,
)
from hep_agent.orchestration import (
    prepare_end_to_end,
)


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)

DEFAULT_SCENARIOS = (
    PROJECT_ROOT
    / "evaluation"
    / "preexecution_scenarios_v1.json"
)

DEFAULT_PROFILES = (
    PROJECT_ROOT
    / "configs"
    / "agent_profiles.json"
)

DEFAULT_OUTPUT_ROOT = (
    PROJECT_ROOT
    / "evaluation"
    / "results"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def _utc_run_label() -> str:
    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )


def _load_scenarios(
    path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    scenarios = payload.get(
        "scenarios"
    )

    if not isinstance(
        scenarios,
        list,
    ):
        raise ValueError(
            "Scenario file must contain "
            "a 'scenarios' list."
        )

    ids = [
        scenario.get("id")
        for scenario in scenarios
    ]

    if (
        any(
            not isinstance(
                scenario_id,
                str,
            )
            for scenario_id in ids
        )
        or len(ids) != len(set(ids))
    ):
        raise ValueError(
            "Scenario IDs must be unique strings."
        )

    return payload, scenarios


def _mean(
    values: Iterable[
        float | int | None
    ],
) -> float | None:
    filtered = [
        float(value)
        for value in values
        if value is not None
    ]

    if not filtered:
        return None

    return statistics.fmean(
        filtered
    )


def _rate(
    values: Iterable[
        bool | None
    ],
) -> float | None:
    filtered = [
        bool(value)
        for value in values
        if value is not None
    ]

    if not filtered:
        return None

    return sum(filtered) / len(filtered)


def _aggregate(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "trials": len(rows),
        "evaluation_passes": sum(
            bool(row["evaluation_pass"])
            for row in rows
        ),
        "evaluation_pass_rate": _rate(
            row["evaluation_pass"]
            for row in rows
        ),
        "ready_rate": _rate(
            row.get("actual_ready")
            for row in rows
        ),
        "first_attempt_grounding_success_rate": _rate(
            row.get(
                "first_attempt_grounding_success"
            )
            for row in rows
        ),
        "final_preexecution_success_rate": _rate(
            row.get(
                "final_preexecution_success"
            )
            for row in rows
        ),
        "fallback_rate": _rate(
            row.get("fallback_used")
            for row in rows
        ),
        "mean_llm_calls": _mean(
            row.get("llm_call_count")
            for row in rows
        ),
        "mean_repair_attempts": _mean(
            row.get("repair_attempts")
            for row in rows
        ),
        "mean_corrections": _mean(
            row.get("corrections_applied")
            for row in rows
        ),
        "mean_model_generation_time_seconds": _mean(
            row.get(
                "model_generation_time_seconds"
            )
            for row in rows
        ),
        "mean_total_wall_time_seconds": _mean(
            row.get(
                "total_wall_time_seconds"
            )
            for row in rows
        ),
        "crashes": sum(
            bool(row.get("crash"))
            for row in rows
        ),
    }


def _write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    columns = [
        "trial_id",
        "scenario_id",
        "scenario_title",
        "profile_name",
        "repeat",
        "evaluation_pass",
        "actual_ready",
        "analysis_mode",
        "status",
        "failure_category",
        "run_id",
        "first_attempt_grounding_success",
        "final_preexecution_success",
        "llm_call_count",
        "repair_attempts",
        "repair_success",
        "fallback_used",
        "corrections_applied",
        "grounding_valid",
        "artifact_valid",
        "invalid_artifact_output",
        "model_generation_time_seconds",
        "total_wall_time_seconds",
        "failed_checks",
        "record_path",
        "crash",
        "exception_type",
        "exception_message",
    ]

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()

        for row in rows:
            writer.writerow(row)


def _summary(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    profile_names = sorted(
        {
            row["profile_name"]
            for row in rows
        }
    )
    scenario_ids = sorted(
        {
            row["scenario_id"]
            for row in rows
        }
    )

    return {
        "overall": _aggregate(rows),
        "by_profile": {
            profile_name: _aggregate(
                [
                    row
                    for row in rows
                    if row["profile_name"]
                    == profile_name
                ]
            )
            for profile_name
            in profile_names
        },
        "by_scenario": {
            scenario_id: _aggregate(
                [
                    row
                    for row in rows
                    if row["scenario_id"]
                    == scenario_id
                ]
            )
            for scenario_id
            in scenario_ids
        },
    }


def _trial_row(
    *,
    trial_id: str,
    scenario: dict[str, Any],
    profile_name: str,
    repeat: int,
    prepared: Any,
) -> dict[str, Any]:
    verdict = evaluate_prepared_scenario(
        prepared,
        scenario,
    )

    record = prepared.record
    failed_checks = [
        check.name
        for check in verdict.checks
        if not check.passed
    ]

    return {
        "trial_id": trial_id,
        "scenario_id": scenario["id"],
        "scenario_title": scenario["title"],
        "profile_name": profile_name,
        "repeat": repeat,
        "evaluation_pass": verdict.passed,
        "actual_ready": prepared.is_ready,
        "analysis_mode": verdict.analysis_mode,
        "status": record.status,
        "failure_category": (
            record.failure_category
        ),
        "run_id": record.run_id,
        "first_attempt_grounding_success": (
            record.first_attempt_grounding_success
        ),
        "final_preexecution_success": (
            record.final_preexecution_success
        ),
        "llm_call_count": record.llm_call_count,
        "repair_attempts": record.repair_attempts,
        "repair_success": record.repair_success,
        "fallback_used": record.fallback_used,
        "corrections_applied": (
            record.corrections_applied
        ),
        "grounding_valid": record.grounding_valid,
        "artifact_valid": record.artifact_valid,
        "invalid_artifact_output": (
            record.invalid_artifact_output
        ),
        "model_generation_time_seconds": (
            record.model_generation_time_seconds
        ),
        "total_wall_time_seconds": (
            record.total_wall_time_seconds
        ),
        "failed_checks": ",".join(
            failed_checks
        ),
        "record_path": str(
            prepared.preexecution.record_path
        ),
        "crash": False,
        "exception_type": None,
        "exception_message": None,
        "verdict": verdict.model_dump(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run frozen local-agent "
            "pre-execution evaluation scenarios."
        )
    )

    parser.add_argument(
        "--scenarios",
        default=str(DEFAULT_SCENARIOS),
    )
    parser.add_argument(
        "--profiles-config",
        default=str(DEFAULT_PROFILES),
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["qwen_primary"],
    )
    parser.add_argument(
        "--scenario-ids",
        nargs="*",
        default=None,
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
    )
    parser.add_argument(
        "--run-label",
        default=None,
    )
    parser.add_argument(
        "--ollama-host",
        default=None,
    )
    parser.add_argument(
        "--sleep-between",
        type=float,
        default=1.0,
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.repeats < 1:
        raise ValueError(
            "--repeats must be at least 1."
        )

    scenarios_path = Path(
        args.scenarios
    ).expanduser().resolve()

    profiles_path = Path(
        args.profiles_config
    ).expanduser().resolve()

    output_root = Path(
        args.output_root
    ).expanduser().resolve()

    if args.ollama_host:
        os.environ[
            "OLLAMA_HOST"
        ] = args.ollama_host

    suite_payload, scenarios = (
        _load_scenarios(
            scenarios_path
        )
    )

    if args.scenario_ids:
        selected = set(
            args.scenario_ids
        )
        known = {
            scenario["id"]
            for scenario in scenarios
        }

        unknown = selected - known

        if unknown:
            raise ValueError(
                "Unknown scenario IDs: "
                + ", ".join(
                    sorted(unknown)
                )
            )

        scenarios = [
            scenario
            for scenario in scenarios
            if scenario["id"] in selected
        ]

    profiles = load_agent_profiles(
        profiles_path
    )

    unknown_profiles = (
        set(args.profiles)
        - set(profiles)
    )

    if unknown_profiles:
        raise ValueError(
            "Unknown profiles: "
            + ", ".join(
                sorted(unknown_profiles)
            )
        )

    run_label = (
        args.run_label
        or _utc_run_label()
    )

    run_root = (
        output_root
        / suite_payload["suite_id"]
        / run_label
    )

    records_directory = (
        run_root / "records"
    )
    trials_directory = (
        run_root / "trials"
    )

    records_directory.mkdir(
        parents=True,
        exist_ok=True,
    )
    trials_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest = {
        "suite_id": suite_payload[
            "suite_id"
        ],
        "suite_schema_version": (
            suite_payload[
                "schema_version"
            ]
        ),
        "scenario_file": str(
            scenarios_path
        ),
        "scenario_sha256": _sha256(
            scenarios_path
        ),
        "profiles_file": str(
            profiles_path
        ),
        "profiles_sha256": _sha256(
            profiles_path
        ),
        "profiles": args.profiles,
        "scenario_ids": [
            scenario["id"]
            for scenario in scenarios
        ],
        "repeats": args.repeats,
        "ollama_host": os.environ.get(
            "OLLAMA_HOST",
            "http://localhost:11434",
        ),
        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }

    (
        run_root / "manifest.json"
    ).write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    rows: list[dict[str, Any]] = []

    jsonl_path = (
        run_root / "trials.jsonl"
    )

    total_trials = (
        len(args.profiles)
        * len(scenarios)
        * args.repeats
    )
    completed = 0

    with jsonl_path.open(
        "a",
        encoding="utf-8",
    ) as jsonl:
        for profile_name in args.profiles:
            profile = profiles[
                profile_name
            ]

            for repeat in range(
                1,
                args.repeats + 1,
            ):
                for scenario in scenarios:
                    completed += 1
                    trial_id = (
                        f"{profile_name}__"
                        f"{scenario['id']}__"
                        f"r{repeat:02d}"
                    )

                    print()
                    print("=" * 72)
                    print(
                        f"[{completed}/{total_trials}] "
                        f"{trial_id}"
                    )
                    print(scenario["title"])
                    print("=" * 72)

                    try:
                        prepared = prepare_end_to_end(
                            scenario["request"],
                            client=OllamaClient(),
                            profile_name=profile_name,
                            profile=profile,
                            records_directory=(
                                records_directory
                            ),
                        )

                        row = _trial_row(
                            trial_id=trial_id,
                            scenario=scenario,
                            profile_name=(
                                profile_name
                            ),
                            repeat=repeat,
                            prepared=prepared,
                        )

                    except Exception as exc:
                        row = {
                            "trial_id": trial_id,
                            "scenario_id": (
                                scenario["id"]
                            ),
                            "scenario_title": (
                                scenario["title"]
                            ),
                            "profile_name": (
                                profile_name
                            ),
                            "repeat": repeat,
                            "evaluation_pass": False,
                            "actual_ready": None,
                            "analysis_mode": None,
                            "status": None,
                            "failure_category": None,
                            "run_id": None,
                            "first_attempt_grounding_success": None,
                            "final_preexecution_success": None,
                            "llm_call_count": None,
                            "repair_attempts": None,
                            "repair_success": None,
                            "fallback_used": None,
                            "corrections_applied": None,
                            "grounding_valid": None,
                            "artifact_valid": None,
                            "invalid_artifact_output": None,
                            "model_generation_time_seconds": None,
                            "total_wall_time_seconds": None,
                            "failed_checks": "runner_exception",
                            "record_path": None,
                            "crash": True,
                            "exception_type": (
                                type(exc).__name__
                            ),
                            "exception_message": str(exc),
                            "verdict": None,
                        }

                    rows.append(row)

                    trial_path = (
                        trials_directory
                        / f"{trial_id}.json"
                    )

                    trial_path.write_text(
                        json.dumps(
                            row,
                            indent=2,
                            sort_keys=True,
                        )
                        + "\n",
                        encoding="utf-8",
                    )

                    jsonl.write(
                        json.dumps(
                            row,
                            sort_keys=True,
                        )
                        + "\n"
                    )
                    jsonl.flush()

                    print(
                        "Evaluation pass:",
                        row[
                            "evaluation_pass"
                        ],
                    )
                    print(
                        "Ready:",
                        row.get(
                            "actual_ready"
                        ),
                    )
                    print(
                        "LLM calls:",
                        row.get(
                            "llm_call_count"
                        ),
                    )
                    print(
                        "Repairs:",
                        row.get(
                            "repair_attempts"
                        ),
                    )
                    print(
                        "Fallback:",
                        row.get(
                            "fallback_used"
                        ),
                    )
                    print(
                        "Failed checks:",
                        row.get(
                            "failed_checks"
                        )
                        or "none",
                    )

                    if (
                        args.sleep_between > 0
                        and completed
                        < total_trials
                    ):
                        time.sleep(
                            args.sleep_between
                        )

    _write_csv(
        run_root / "trials.csv",
        rows,
    )

    summary = _summary(rows)

    (
        run_root / "summary.json"
    ).write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print("PRE-EXECUTION EVALUATION FINISHED")
    print("=" * 72)
    print("Output:", run_root)
    print(
        "Trials:",
        summary["overall"]["trials"],
    )
    print(
        "Passed:",
        summary["overall"][
            "evaluation_passes"
        ],
    )
    print(
        "Pass rate:",
        summary["overall"][
            "evaluation_pass_rate"
        ],
    )
    print(
        "Crashes:",
        summary["overall"]["crashes"],
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
