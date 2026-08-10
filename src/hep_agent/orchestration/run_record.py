"""Save reproducible records of local-agent pre-execution runs."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hep_agent.execution import (
    MadGraphExecutionResult,
    MadGraphPhysicsResult,
)
from hep_agent.execution.outcome import (
    ExecutionOutputValidation,
    OUTPUT_VALIDATION_FAILURE,
)
from hep_agent.orchestration.analysis_stage import (
    AnalysisStageResult,
)
from hep_agent.models import (
    AgentProfile,
    OllamaClient,
    default_planner_prompt_path,
    default_repair_prompt_path,
)
from hep_agent.models.semantic_process import (
    SEMANTIC_PROCESS_PROMPT,
)
from hep_agent.orchestration.preexecution import (
    PreExecutionResult,
    ProgressObserver,
    run_preexecution_loop,
)


class PreExecutionRunRecord(BaseModel):
    """JSON-serializable record of one pre-execution agent run."""

    model_config = ConfigDict(extra="forbid")

    record_version: str = "1.1"
    run_id: str
    created_at_utc: str

    agent_profile_name: str
    agent_profile: dict[str, Any]
    profile_sha256: str

    planner_prompt_sha256: str
    repair_prompt_sha256: str
    semantic_prompt_sha256: str

    user_request: str
    status: str

    failure_category: str | None = None
    failure_message: str | None = None

    first_attempt_grounding_success: bool | None = None
    final_preexecution_success: bool

    llm_call_count: int = Field(ge=0)
    repair_attempts: int = Field(ge=0)
    repair_success: bool | None = None
    fallback_used: bool

    model_generation_time_seconds: float
    total_wall_time_seconds: float

    corrections_applied: int = Field(ge=0)
    corrections: list[dict[str, Any]]
    model_calls: list[dict[str, Any]]

    grounding_valid: bool | None = None
    artifact_valid: bool | None = None
    invalid_artifact_output: bool | None = None

    approval: dict[str, Any] | None = None
    workflow: dict[str, Any] | None = None
    artifact_commands: list[str] | None = None

    final_status: str | None = None
    approval_obtained: bool | None = None

    execution_started: bool = False
    execution_success: bool | None = None
    execution_failure_category: str | None = None
    execution_returncode: int | None = None
    execution_wall_time_seconds: float | None = None

    execution_directory: str | None = None
    command_script_path: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None

    physics_summary_found: bool | None = None
    cross_section_pb: float | None = None
    cross_section_uncertainty_pb: float | None = None
    generated_event_count: int | None = None
    primary_lhe_file: str | None = None
    showered_hepmc_file: str | None = None
    detector_root_file: str | None = None
    missing_requested_outputs: list[str] = Field(
        default_factory=list
    )
    execution_warnings: list[str] = Field(default_factory=list)

    analysis_requested: bool = False
    analysis_started: bool = False
    analysis_success: bool | None = None
    analysis_failure_category: str | None = None
    analysis_failure_message: str | None = None

    analysis_level: str | None = None
    analysis_input_file: str | None = None
    analysis_directory: str | None = None
    analysis_script_path: str | None = None
    analysis_stdout_path: str | None = None
    analysis_stderr_path: str | None = None

    analysis_returncode: int | None = None
    analysis_wall_time_seconds: float | None = None
    analysis_html_report: str | None = None
    analysis_pdf_report: str | None = None
    analysis_plot_files: list[str] = Field(default_factory=list)
    analysis_internal_error_lines: list[str] = Field(
        default_factory=list
    )

    end_to_end_wall_time_seconds: float | None = None


@dataclass(frozen=True)
class RecordedPreExecution:
    """Pre-execution result together with its saved JSON record."""

    result: PreExecutionResult
    record: PreExecutionRunRecord
    record_path: Path


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Calculate the SHA-256 hash of one file."""

    return _sha256_bytes(Path(path).read_bytes())


def sha256_text(content: str) -> str:
    """Calculate the SHA-256 hash of one exact text string."""

    return _sha256_bytes(content.encode("utf-8"))


def _profile_sha256(profile: AgentProfile) -> str:
    payload = json.dumps(
        profile.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return _sha256_bytes(payload)


def _make_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S"
    )
    suffix = uuid.uuid4().hex[:8]
    return f"{timestamp}_{suffix}"


def build_preexecution_run_record(
    *,
    result: PreExecutionResult,
    profile_name: str,
    profile: AgentProfile,
    total_wall_time_seconds: float,
    run_id: str | None = None,
) -> PreExecutionRunRecord:
    """Convert a PreExecutionResult into a reproducible JSON record."""

    model_generation_time = sum(
        call.duration_seconds or 0.0
        for call in result.model_calls
    )

    if result.grounding_report is None:
        first_attempt_grounding_success = None
        grounding_valid = None
    else:
        first_attempt_grounding_success = (
            result.grounding_report.is_valid
            and not result.corrections
            and result.repair_attempts == 0
            and not result.fallback_used
        )
        grounding_valid = result.grounding_report.is_valid

    if result.repair_attempts > 0 or result.fallback_used:
        repair_success: bool | None = result.is_ready
    else:
        repair_success = None

    artifact_valid = (
        result.artifact_report.is_valid
        if result.artifact_report is not None
        else None
    )

    invalid_artifact_output = (
        not result.artifact_report.is_valid
        if result.artifact_report is not None
        else None
    )

    corrections = [
        {
            "path": item.path,
            "previous_value": item.previous_value,
            "corrected_value": item.corrected_value,
            "reason": item.reason,
            "requires_confirmation": (
                item.requires_confirmation
            ),
        }
        for item in result.corrections
    ]

    model_calls = [
        {
            "role": call.role,
            "model": call.model,
            "duration_seconds": call.duration_seconds,
        }
        for call in result.model_calls
    ]

    approval = None

    if result.approval is not None:
        approval = {
            "decision": result.approval.decision.value,
            "reasons": list(result.approval.reasons),
            "auto_confirm_delay_seconds": (
                result.approval.auto_confirm_delay_seconds
            ),
        }

    workflow = (
        result.workflow.model_dump(mode="json")
        if result.workflow is not None
        else None
    )

    artifact_commands = (
        list(result.artifact.commands)
        if result.artifact is not None
        else None
    )

    failure_category = (
        result.failure_category.value
        if result.failure_category is not None
        else None
    )

    created_at = datetime.now(timezone.utc).isoformat().replace(
        "+00:00",
        "Z",
    )

    return PreExecutionRunRecord(
        run_id=run_id or _make_run_id(),
        created_at_utc=created_at,
        agent_profile_name=profile_name,
        agent_profile=profile.model_dump(mode="json"),
        profile_sha256=_profile_sha256(profile),
        planner_prompt_sha256=sha256_file(
            default_planner_prompt_path()
        ),
        repair_prompt_sha256=sha256_file(
            default_repair_prompt_path()
        ),
        semantic_prompt_sha256=sha256_text(
            SEMANTIC_PROCESS_PROMPT
        ),
        user_request=result.user_request,
        status=result.status.value,
        failure_category=failure_category,
        failure_message=result.failure_message,
        first_attempt_grounding_success=(
            first_attempt_grounding_success
        ),
        final_preexecution_success=result.is_ready,
        llm_call_count=result.llm_call_count,
        repair_attempts=result.repair_attempts,
        repair_success=repair_success,
        fallback_used=result.fallback_used,
        model_generation_time_seconds=model_generation_time,
        total_wall_time_seconds=total_wall_time_seconds,
        corrections_applied=len(corrections),
        corrections=corrections,
        model_calls=model_calls,
        grounding_valid=grounding_valid,
        artifact_valid=artifact_valid,
        invalid_artifact_output=invalid_artifact_output,
        approval=approval,
        workflow=workflow,
        artifact_commands=artifact_commands,
    )


def save_run_record(
    record: PreExecutionRunRecord,
    output_directory: str | Path,
) -> Path:
    """Save one run record using an atomic file replacement."""

    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    target = output_dir / f"{record.run_id}.json"
    temporary = output_dir / f".{record.run_id}.json.tmp"

    content = json.dumps(
        record.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
    ) + "\n"

    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()

    return target


def run_preexecution_and_record(
    user_request: str,
    *,
    client: OllamaClient,
    profile_name: str,
    profile: AgentProfile,
    output_directory: str | Path = "results/runs",
    progress_observer: ProgressObserver | None = None,
) -> RecordedPreExecution:
    """Run the pre-execution agent and save its complete record."""

    start = time.perf_counter()

    result = run_preexecution_loop(
        user_request,
        client=client,
        profile=profile,
        progress_observer=progress_observer,
    )

    total_wall_time = time.perf_counter() - start

    record = build_preexecution_run_record(
        result=result,
        profile_name=profile_name,
        profile=profile,
        total_wall_time_seconds=total_wall_time,
    )

    record_path = save_run_record(
        record,
        output_directory,
    )

    return RecordedPreExecution(
        result=result,
        record=record,
        record_path=record_path,
    )


def _portable_path(
    path: str | Path | None,
    *,
    project_root: str | Path,
) -> str | None:
    """Store a project-relative path whenever possible."""

    if path is None:
        return None

    resolved = Path(path).expanduser().resolve()
    root = Path(project_root).expanduser().resolve()

    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def update_record_after_execution(
    record: PreExecutionRunRecord,
    *,
    execution: MadGraphExecutionResult,
    physics: MadGraphPhysicsResult | None,
    analysis: AnalysisStageResult | None,
    output_validation: ExecutionOutputValidation,
    analysis_was_requested: bool,
    execution_directory: str | Path,
    project_root: str | Path = ".",
    end_to_end_wall_time_seconds: float | None = None,
) -> PreExecutionRunRecord:
    """Add execution and parsed physics results to one run record."""

    validated_execution_success = output_validation.is_valid

    failure_category = (
        execution.failure_category.value
        if execution.failure_category is not None
        else None
    )

    if (
        execution.success
        and not validated_execution_success
        and failure_category is None
    ):
        failure_category = (
            OUTPUT_VALIDATION_FAILURE
        )

    physics_summary_found = (
        physics.has_physics_summary
        if physics is not None
        else (
            False
            if execution.success
            else None
        )
    )

    analysis_requested = analysis_was_requested
    analysis_execution = (
        analysis.execution
        if analysis is not None
        else None
    )

    if not validated_execution_success:
        final_status = "execution_failed"
    elif (
        analysis is not None
        and analysis.requested
        and not analysis.success
    ):
        final_status = "analysis_failed"
    elif (
        analysis is not None
        and analysis.requested
        and analysis.success
    ):
        final_status = "analysis_succeeded"
    else:
        final_status = "execution_succeeded"

    analysis_failure_category = (
        analysis.failure_category.value
        if (
            analysis is not None
            and analysis.failure_category is not None
        )
        else None
    )

    analysis_level = (
        analysis.selection.level.value
        if (
            analysis is not None
            and analysis.selection is not None
        )
        else None
    )

    analysis_input_file = (
        analysis.selection.input_file
        if (
            analysis is not None
            and analysis.selection is not None
        )
        else None
    )

    return record.model_copy(
        update={
            "final_status": final_status,
            "approval_obtained": True,
            "execution_started": True,
            "execution_success": (
                validated_execution_success
            ),
            "execution_failure_category": failure_category,
            "execution_returncode": execution.returncode,
            "execution_wall_time_seconds": (
                execution.wall_time_seconds
            ),
            "execution_directory": _portable_path(
                execution_directory,
                project_root=project_root,
            ),
            "command_script_path": _portable_path(
                execution.command_script_path,
                project_root=project_root,
            ),
            "stdout_path": _portable_path(
                execution.stdout_path,
                project_root=project_root,
            ),
            "stderr_path": _portable_path(
                execution.stderr_path,
                project_root=project_root,
            ),
            "physics_summary_found": physics_summary_found,
            "cross_section_pb": (
                physics.cross_section_pb
                if physics is not None
                else None
            ),
            "cross_section_uncertainty_pb": (
                physics.cross_section_uncertainty_pb
                if physics is not None
                else None
            ),
            "generated_event_count": (
                physics.event_count
                if physics is not None
                else None
            ),
            "primary_lhe_file": _portable_path(
                (
                    physics.primary_lhe_file
                    if physics is not None
                    else None
                ),
                project_root=project_root,
            ),
            "showered_hepmc_file": _portable_path(
                (
                    physics.showered_hepmc_file
                    if physics is not None
                    else None
                ),
                project_root=project_root,
            ),
            "detector_root_file": _portable_path(
                (
                    physics.detector_root_file
                    if physics is not None
                    else None
                ),
                project_root=project_root,
            ),
            "missing_requested_outputs": list(
                output_validation.missing_requested_outputs
            ),
            "execution_warnings": list(
                dict.fromkeys(
                    (
                        list(physics.warnings)
                        if physics is not None
                        else []
                    )
                    + [
                        f"requested_output_not_found:{name}"
                        for name in (
                            output_validation
                            .missing_requested_outputs
                        )
                    ]
                )
            ),
            "analysis_requested": analysis_requested,
            "analysis_started": (
                analysis_execution is not None
            ),
            "analysis_success": (
                analysis.success
                if (
                    analysis is not None
                    and analysis.requested
                )
                else None
            ),
            "analysis_failure_category": (
                analysis_failure_category
            ),
            "analysis_failure_message": (
                analysis.failure_message
                if analysis is not None
                else None
            ),
            "analysis_level": analysis_level,
            "analysis_input_file": _portable_path(
                analysis_input_file,
                project_root=project_root,
            ),
            "analysis_directory": _portable_path(
                (
                    analysis_execution.script_path.parent
                    if analysis_execution is not None
                    else None
                ),
                project_root=project_root,
            ),
            "analysis_script_path": _portable_path(
                (
                    analysis_execution.script_path
                    if analysis_execution is not None
                    else None
                ),
                project_root=project_root,
            ),
            "analysis_stdout_path": _portable_path(
                (
                    analysis_execution.stdout_path
                    if analysis_execution is not None
                    else None
                ),
                project_root=project_root,
            ),
            "analysis_stderr_path": _portable_path(
                (
                    analysis_execution.stderr_path
                    if analysis_execution is not None
                    else None
                ),
                project_root=project_root,
            ),
            "analysis_returncode": (
                analysis_execution.returncode
                if analysis_execution is not None
                else None
            ),
            "analysis_wall_time_seconds": (
                analysis_execution.wall_time_seconds
                if analysis_execution is not None
                else None
            ),
            "analysis_html_report": _portable_path(
                (
                    analysis_execution.html_report
                    if analysis_execution is not None
                    else None
                ),
                project_root=project_root,
            ),
            "analysis_pdf_report": _portable_path(
                (
                    analysis_execution.pdf_report
                    if analysis_execution is not None
                    else None
                ),
                project_root=project_root,
            ),
            "analysis_plot_files": [
                _portable_path(
                    plot,
                    project_root=project_root,
                )
                for plot in (
                    analysis_execution.plot_files
                    if analysis_execution is not None
                    else ()
                )
            ],
            "analysis_internal_error_lines": (
                list(
                    analysis_execution.internal_error_lines
                )
                if analysis_execution is not None
                else []
            ),
            "end_to_end_wall_time_seconds": (
                end_to_end_wall_time_seconds
            ),
        }
    )


def mark_record_cancelled(
    record: PreExecutionRunRecord,
    *,
    end_to_end_wall_time_seconds: float | None = None,
) -> PreExecutionRunRecord:
    """Mark a validated run as cancelled before execution."""

    return record.model_copy(
        update={
            "final_status": "cancelled",
            "approval_obtained": False,
            "execution_started": False,
            "end_to_end_wall_time_seconds": (
                end_to_end_wall_time_seconds
            ),
        }
    )
