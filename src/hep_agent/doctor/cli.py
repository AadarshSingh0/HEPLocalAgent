"""Command-line interface for the HEP-agent doctor."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from hep_agent.doctor.checks import (
    DEFAULT_PROFILE,
    default_project_root,
    run_doctor,
)
from hep_agent.doctor.render import (
    render_text_report,
)


def _safe_timestamp() -> str:
    return datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")


def _save_report(
    report_payload: dict,
    *,
    project_root: Path,
) -> tuple[Path, Path]:
    output_directory = (
        project_root
        / "results"
        / "doctor"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamped = (
        output_directory
        / (
            "doctor_"
            f"{_safe_timestamp()}.json"
        )
    )

    latest = (
        output_directory
        / "latest.json"
    )

    text = (
        json.dumps(
            report_payload,
            indent=2,
        )
        + "\n"
    )

    timestamped.write_text(
        text,
        encoding="utf-8",
    )

    latest.write_text(
        text,
        encoding="utf-8",
    )

    return timestamped, latest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose the HEP-agent runtime, "
            "model service, and HEP tools."
        )
    )

    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help=(
            "Agent profile to validate "
            f"(default: {DEFAULT_PROFILE})."
        ),
    )

    parser.add_argument(
        "--ollama-host",
        default=None,
        help=(
            "Override OLLAMA_HOST for this check."
        ),
    )

    parser.add_argument(
        "--deep",
        action="store_true",
        help=(
            "Run a live model request and temporary "
            "MG5 process-generation test."
        ),
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help=(
            "Timeout for deep checks in seconds."
        ),
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON instead of text.",
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help=(
            "Save timestamped and latest JSON reports "
            "under results/doctor/."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = default_project_root()

    report = run_doctor(
        project_root=root,
        selected_profile=args.profile,
        ollama_host=args.ollama_host,
        deep=args.deep,
        timeout_seconds=args.timeout,
    )

    payload = report.to_dict()

    if args.json:
        print(
            json.dumps(
                payload,
                indent=2,
            )
        )
    else:
        print(
            render_text_report(
                report
            )
        )

    if args.save:
        timestamped, latest = (
            _save_report(
                payload,
                project_root=root,
            )
        )

        print()
        print(
            "Saved:",
            timestamped,
        )
        print(
            "Updated:",
            latest,
        )

    return 0 if report.healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
