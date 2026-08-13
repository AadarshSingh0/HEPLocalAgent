#!/usr/bin/env python3
"""Noninteractive startup smoke test for one configured MA5 runtime."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from hep_agent.analysis.runtime import (  # noqa: E402
    MadAnalysisRuntimeConfigurationError,
    build_madanalysis_environment,
    load_madanalysis_runtime,
    verify_root_metadata,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ma5", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.timeout_seconds <= 0:
        print("timeout-seconds must be positive", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[A-Za-z0-9_-]+", arguments.attempt):
        print("attempt must contain only letters, digits, _ or -", file=sys.stderr)
        return 2

    executable = arguments.ma5.expanduser().resolve()
    output_directory = arguments.output_directory.expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    script_path = output_directory / "smoke.ma5"
    stdout_path = output_directory / f"stdout-{arguments.attempt}.log"
    stderr_path = output_directory / f"stderr-{arguments.attempt}.log"
    script_path.write_text("quit\n", encoding="utf-8")

    print(f"MadAnalysis5 smoke stdout: {stdout_path}")
    print(f"MadAnalysis5 smoke stderr: {stderr_path}")

    try:
        runtime = load_madanalysis_runtime(executable)
        if runtime is not None:
            verify_root_metadata(runtime)
        environment = build_madanalysis_environment(executable)
        completed = subprocess.run(
            [str(executable), "-H", "-f", "-s", str(script_path)],
            cwd=output_directory,
            capture_output=True,
            text=True,
            timeout=arguments.timeout_seconds,
            check=False,
            env=environment,
        )
    except MadAnalysisRuntimeConfigurationError as exc:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(str(exc) + "\n", encoding="utf-8")
        print(f"MadAnalysis5 runtime configuration error: {exc}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        print("MadAnalysis5 smoke test timed out.", file=sys.stderr)
        return 1
    except OSError as exc:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(str(exc) + "\n", encoding="utf-8")
        print(f"Could not start MadAnalysis5: {exc}", file=sys.stderr)
        return 1

    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    combined_lines = (
        completed.stdout.splitlines() + completed.stderr.splitlines()
    )
    errors = [line.strip() for line in combined_lines if "MA5-ERROR" in line]

    if completed.returncode != 0:
        print(
            f"MadAnalysis5 smoke test exited with code "
            f"{completed.returncode}.",
            file=sys.stderr,
        )
        return 1
    if errors:
        print("MadAnalysis5 smoke test reported MA5-ERROR:", file=sys.stderr)
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        return 1
    if (
        "MA5 release" not in completed.stdout
        or "Checking the MadAnalysis 5 core library" not in completed.stdout
    ):
        print(
            "MadAnalysis5 did not complete its startup/core-library checks.",
            file=sys.stderr,
        )
        return 1

    print("MadAnalysis5 noninteractive smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
