"""Safe subprocess runner for validated MadGraph workflows.

This module executes a previously validated MadGraphWorkflowArtifact.

It does not build physics commands, call an LLM, or repair failures.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from hep_agent.builders import MadGraphWorkflowArtifact
from hep_agent.runtime import (
    StackConfigurationError,
    build_stack_environment,
    load_stack_manifest,
)


class ExecutionFailureCategory(str, Enum):
    CONFIGURATION = "configuration_failure"
    START_FAILURE = "start_failure"
    TIMEOUT = "timeout"
    NONZERO_EXIT = "nonzero_exit"


@dataclass(frozen=True)
class MadGraphExecutionResult:
    """Result of one MadGraph subprocess invocation."""

    success: bool
    command_script_path: Path
    stdout_path: Path | None
    stderr_path: Path | None

    returncode: int | None
    wall_time_seconds: float

    failure_category: ExecutionFailureCategory | None = None
    failure_message: str | None = None


def _as_text(value: str | bytes | None) -> str:
    """Convert subprocess output into normal text."""

    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    return value


def _write_log(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def run_madgraph_workflow(
    artifact: MadGraphWorkflowArtifact,
    *,
    mg5_executable: str | Path,
    run_directory: str | Path,
    timeout_seconds: float = 1800,
    stack_manifest: str | Path | None = None,
) -> MadGraphExecutionResult:
    """Execute one validated MG5 command file safely.

    The subprocess is launched without shell=True.
    """

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive.")

    run_dir = Path(run_directory).expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    command_script = run_dir / "commands.mg5"
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"

    command_script.write_text(
        artifact.text,
        encoding="utf-8",
    )

    executable = Path(mg5_executable).expanduser().resolve()

    if not executable.is_file():
        return MadGraphExecutionResult(
            success=False,
            command_script_path=command_script,
            stdout_path=None,
            stderr_path=None,
            returncode=None,
            wall_time_seconds=0.0,
            failure_category=ExecutionFailureCategory.CONFIGURATION,
            failure_message=(
                f"MadGraph executable does not exist: {executable}"
            ),
        )

    if not os.access(executable, os.X_OK):
        return MadGraphExecutionResult(
            success=False,
            command_script_path=command_script,
            stdout_path=None,
            stderr_path=None,
            returncode=None,
            wall_time_seconds=0.0,
            failure_category=ExecutionFailureCategory.CONFIGURATION,
            failure_message=(
                f"MadGraph executable is not executable: {executable}"
            ),
        )

    process_environment = None
    if stack_manifest is not None:
        try:
            manifest_root = (
                Path(stack_manifest).expanduser().absolute().parent.parent
            )
            manifest = load_stack_manifest(
                stack_manifest,
                expected_repository_root=manifest_root,
            )
            expected = manifest.executable("madgraph").resolve()
            if executable.resolve() != expected:
                raise StackConfigurationError(
                    "Configured MadGraph executable disagrees with the "
                    f"managed stack manifest: {executable}; expected {expected}."
                )
            process_environment = build_stack_environment(manifest)
        except StackConfigurationError as exc:
            return MadGraphExecutionResult(
                success=False,
                command_script_path=command_script,
                stdout_path=None,
                stderr_path=None,
                returncode=None,
                wall_time_seconds=0.0,
                failure_category=ExecutionFailureCategory.CONFIGURATION,
                failure_message=str(exc),
            )

    start = time.perf_counter()

    try:
        completed = subprocess.run(
            [str(executable), str(command_script)],
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=process_environment,
        )

    except subprocess.TimeoutExpired as exc:
        wall_time = time.perf_counter() - start

        stdout = _as_text(exc.stdout)
        stderr = _as_text(exc.stderr)

        _write_log(stdout_path, stdout)
        _write_log(stderr_path, stderr)

        return MadGraphExecutionResult(
            success=False,
            command_script_path=command_script,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            returncode=None,
            wall_time_seconds=wall_time,
            failure_category=ExecutionFailureCategory.TIMEOUT,
            failure_message=(
                f"MadGraph exceeded the {timeout_seconds:g}-second "
                "execution timeout."
            ),
        )

    except OSError as exc:
        wall_time = time.perf_counter() - start

        _write_log(stdout_path, "")
        _write_log(stderr_path, str(exc))

        return MadGraphExecutionResult(
            success=False,
            command_script_path=command_script,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            returncode=None,
            wall_time_seconds=wall_time,
            failure_category=ExecutionFailureCategory.START_FAILURE,
            failure_message=f"Could not start MadGraph: {exc}",
        )

    wall_time = time.perf_counter() - start

    _write_log(stdout_path, completed.stdout)
    _write_log(stderr_path, completed.stderr)

    if completed.returncode != 0:
        return MadGraphExecutionResult(
            success=False,
            command_script_path=command_script,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            returncode=completed.returncode,
            wall_time_seconds=wall_time,
            failure_category=ExecutionFailureCategory.NONZERO_EXIT,
            failure_message=(
                "MadGraph exited with return code "
                f"{completed.returncode}."
            ),
        )

    return MadGraphExecutionResult(
        success=True,
        command_script_path=command_script,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        returncode=completed.returncode,
        wall_time_seconds=wall_time,
    )
