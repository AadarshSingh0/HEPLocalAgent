"""Safe subprocess execution for deterministic MadAnalysis artifacts."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from hep_agent.analysis.madanalysis import (
    MadAnalysisArtifact,
    validate_madanalysis_artifact,
)
from hep_agent.analysis.runtime import (
    MadAnalysisRuntimeConfigurationError,
    build_madanalysis_environment,
    load_madanalysis_runtime,
    verify_root_metadata,
)
from hep_agent.runtime import (
    StackConfigurationError,
    build_stack_environment,
    load_stack_manifest,
)


class MadAnalysisFailureCategory(str, Enum):
    """Failure classes for one MadAnalysis execution."""

    ARTIFACT_VALIDATION = "artifact_validation_failure"
    CONFIGURATION = "configuration_failure"
    START_FAILURE = "start_failure"
    TIMEOUT = "timeout"
    NONZERO_EXIT = "nonzero_exit"
    INTERNAL_ERROR = "madanalysis_internal_error"
    MISSING_REPORT = "missing_report"
    PLOT_COUNT_MISMATCH = "plot_count_mismatch"


@dataclass(frozen=True)
class MadAnalysisExecutionResult:
    """Result of one deterministic MadAnalysis run."""

    success: bool

    script_path: Path
    stdout_path: Path | None
    stderr_path: Path | None

    returncode: int | None
    wall_time_seconds: float

    html_report: Path | None = None
    pdf_report: Path | None = None
    plot_files: tuple[Path, ...] = ()
    internal_error_lines: tuple[str, ...] = ()

    failure_category: MadAnalysisFailureCategory | None = None
    failure_message: str | None = None


def _as_text(value: str | bytes | None) -> str:
    """Convert subprocess output to ordinary text."""

    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode(
            "utf-8",
            errors="replace",
        )

    return value


def _write_text(path: Path, content: str) -> Path:
    """Write one UTF-8 log file."""

    path.write_text(
        content,
        encoding="utf-8",
    )
    return path


def _find_html_report(
    job_directory: Path,
) -> Path | None:
    """Find the generated MA5 HTML report."""

    matches = sorted(
        job_directory.glob(
            "Output/HTML/*/index.html"
        )
    )

    return matches[0] if matches else None


def _find_pdf_report(
    job_directory: Path,
) -> Path | None:
    """Find the generated MA5 PDF report."""

    matches = sorted(
        job_directory.glob(
            "Output/PDF/*/main.pdf"
        )
    )

    return matches[0] if matches else None


def _find_plot_files(
    job_directory: Path,
) -> tuple[Path, ...]:
    """Find generated HTML histogram images."""

    return tuple(
        sorted(
            job_directory.glob(
                "Output/HTML/*/selection_*.png"
            )
        )
    )


def _internal_error_lines(
    stdout_text: str,
    stderr_text: str,
) -> tuple[str, ...]:
    """Collect MA5 internal errors from both output streams."""

    lines = (
        stdout_text.splitlines()
        + stderr_text.splitlines()
    )

    return tuple(
        line.strip()
        for line in lines
        if "MA5-ERROR" in line
    )


def run_madanalysis_artifact(
    artifact: MadAnalysisArtifact,
    *,
    madanalysis_executable: str | Path,
    analysis_directory: str | Path,
    timeout_seconds: float = 300,
    stack_manifest: str | Path | None = None,
    unsupported_nonhermetic: bool = False,
) -> MadAnalysisExecutionResult:
    """Execute one validated MA5 artifact without using a shell."""

    if timeout_seconds <= 0:
        raise ValueError(
            "timeout_seconds must be positive."
        )

    analysis_dir = (
        Path(analysis_directory)
        .expanduser()
        .resolve()
    )
    analysis_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    script_path = analysis_dir / "analysis.ma5"
    stdout_path = analysis_dir / "stdout.log"
    stderr_path = analysis_dir / "stderr.log"

    script_path.write_text(
        artifact.text,
        encoding="utf-8",
    )

    validation = validate_madanalysis_artifact(
        artifact
    )

    if not validation.is_valid:
        message = "; ".join(
            issue.message
            for issue in validation.issues
        )

        return MadAnalysisExecutionResult(
            success=False,
            script_path=script_path,
            stdout_path=None,
            stderr_path=None,
            returncode=None,
            wall_time_seconds=0.0,
            failure_category=(
                MadAnalysisFailureCategory
                .ARTIFACT_VALIDATION
            ),
            failure_message=message,
        )

    if not artifact.input_file.is_file():
        return MadAnalysisExecutionResult(
            success=False,
            script_path=script_path,
            stdout_path=None,
            stderr_path=None,
            returncode=None,
            wall_time_seconds=0.0,
            failure_category=(
                MadAnalysisFailureCategory
                .CONFIGURATION
            ),
            failure_message=(
                "MadAnalysis input event file "
                f"does not exist: {artifact.input_file}"
            ),
        )

    executable = (
        Path(madanalysis_executable)
        .expanduser()
        .resolve()
    )

    if not executable.is_file():
        return MadAnalysisExecutionResult(
            success=False,
            script_path=script_path,
            stdout_path=None,
            stderr_path=None,
            returncode=None,
            wall_time_seconds=0.0,
            failure_category=(
                MadAnalysisFailureCategory
                .CONFIGURATION
            ),
            failure_message=(
                "MadAnalysis executable does not "
                f"exist: {executable}"
            ),
        )

    if not os.access(executable, os.X_OK):
        return MadAnalysisExecutionResult(
            success=False,
            script_path=script_path,
            stdout_path=None,
            stderr_path=None,
            returncode=None,
            wall_time_seconds=0.0,
            failure_category=(
                MadAnalysisFailureCategory
                .CONFIGURATION
            ),
            failure_message=(
                "MadAnalysis executable is not "
                f"executable: {executable}"
            ),
        )

    if stack_manifest is None and not unsupported_nonhermetic:
        message = (
            "Managed stack manifest is required. Unmanaged execution requires "
            "the explicit unsupported_nonhermetic opt-in."
        )
        _write_text(stdout_path, "")
        _write_text(stderr_path, message)
        return MadAnalysisExecutionResult(
            success=False,
            script_path=script_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            returncode=None,
            wall_time_seconds=0.0,
            failure_category=MadAnalysisFailureCategory.CONFIGURATION,
            failure_message=message,
        )

    try:
        if stack_manifest is not None:
            manifest_root = (
                Path(stack_manifest).expanduser().absolute().parent.parent
            )
            manifest = load_stack_manifest(
                stack_manifest,
                expected_repository_root=manifest_root,
            )
            expected = manifest.executable("madanalysis5").resolve()
            if executable.resolve() != expected:
                raise StackConfigurationError(
                    "Configured MadAnalysis executable disagrees with the "
                    f"managed stack manifest: {executable}; expected {expected}."
                )
            process_environment = build_stack_environment(manifest)
        else:
            runtime = load_madanalysis_runtime(executable)
            if runtime is not None:
                verify_root_metadata(runtime)
            process_environment = build_madanalysis_environment(executable)
    except (MadAnalysisRuntimeConfigurationError, StackConfigurationError) as exc:
        _write_text(stdout_path, "")
        _write_text(stderr_path, str(exc))
        return MadAnalysisExecutionResult(
            success=False,
            script_path=script_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            returncode=None,
            wall_time_seconds=0.0,
            failure_category=(
                MadAnalysisFailureCategory.CONFIGURATION
            ),
            failure_message=str(exc),
        )

    start = time.perf_counter()

    try:
        completed = subprocess.run(
            [
                str(executable),
                artifact.mode_flag,
                "-f",
                "-s",
                str(script_path),
            ],
            cwd=str(analysis_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=process_environment,
        )

    except subprocess.TimeoutExpired as exc:
        wall_time = time.perf_counter() - start

        stdout_text = _as_text(exc.stdout)
        stderr_text = _as_text(exc.stderr)

        _write_text(stdout_path, stdout_text)
        _write_text(stderr_path, stderr_text)

        return MadAnalysisExecutionResult(
            success=False,
            script_path=script_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            returncode=None,
            wall_time_seconds=wall_time,
            internal_error_lines=(
                _internal_error_lines(
                    stdout_text,
                    stderr_text,
                )
            ),
            failure_category=(
                MadAnalysisFailureCategory.TIMEOUT
            ),
            failure_message=(
                "MadAnalysis exceeded the "
                f"{timeout_seconds:g}-second timeout."
            ),
        )

    except OSError as exc:
        wall_time = time.perf_counter() - start

        _write_text(stdout_path, "")
        _write_text(stderr_path, str(exc))

        return MadAnalysisExecutionResult(
            success=False,
            script_path=script_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            returncode=None,
            wall_time_seconds=wall_time,
            failure_category=(
                MadAnalysisFailureCategory
                .START_FAILURE
            ),
            failure_message=(
                f"Could not start MadAnalysis: {exc}"
            ),
        )

    wall_time = time.perf_counter() - start

    _write_text(
        stdout_path,
        completed.stdout,
    )
    _write_text(
        stderr_path,
        completed.stderr,
    )

    errors = _internal_error_lines(
        completed.stdout,
        completed.stderr,
    )

    html_report = _find_html_report(
        artifact.job_directory
    )
    pdf_report = _find_pdf_report(
        artifact.job_directory
    )
    plot_files = _find_plot_files(
        artifact.job_directory
    )

    common = {
        "script_path": script_path,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "returncode": completed.returncode,
        "wall_time_seconds": wall_time,
        "html_report": html_report,
        "pdf_report": pdf_report,
        "plot_files": plot_files,
        "internal_error_lines": errors,
    }

    if completed.returncode != 0:
        return MadAnalysisExecutionResult(
            success=False,
            **common,
            failure_category=(
                MadAnalysisFailureCategory
                .NONZERO_EXIT
            ),
            failure_message=(
                "MadAnalysis exited with return code "
                f"{completed.returncode}."
            ),
        )

    if errors:
        return MadAnalysisExecutionResult(
            success=False,
            **common,
            failure_category=(
                MadAnalysisFailureCategory
                .INTERNAL_ERROR
            ),
            failure_message=(
                "MadAnalysis reported one or more "
                "MA5-ERROR messages."
            ),
        )

    if (
        html_report is None
        or pdf_report is None
    ):
        missing: list[str] = []

        if html_report is None:
            missing.append("HTML")

        if pdf_report is None:
            missing.append("PDF")

        return MadAnalysisExecutionResult(
            success=False,
            **common,
            failure_category=(
                MadAnalysisFailureCategory
                .MISSING_REPORT
            ),
            failure_message=(
                "MadAnalysis did not generate the "
                f"expected {' and '.join(missing)} "
                "report."
            ),
        )

    if (
        len(plot_files)
        != artifact.expected_plot_count
    ):
        return MadAnalysisExecutionResult(
            success=False,
            **common,
            failure_category=(
                MadAnalysisFailureCategory
                .PLOT_COUNT_MISMATCH
            ),
            failure_message=(
                "MadAnalysis generated "
                f"{len(plot_files)} plots, but "
                f"{artifact.expected_plot_count} "
                "were expected."
            ),
        )

    return MadAnalysisExecutionResult(
        success=True,
        **common,
    )
