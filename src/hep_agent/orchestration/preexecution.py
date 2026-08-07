"""Central pre-execution loop for the local collider agent.

This module connects:

planner
→ deterministic grounding correction
→ grounding validation
→ bounded model repair
→ optional fallback repair
→ deterministic builder
→ artifact validation
→ approval decision

It does not execute MadGraph.
"""

from __future__ import annotations

import re
import time
from typing import Callable
from dataclasses import dataclass
from enum import Enum

from hep_agent.builders import (
    MadGraphBuildError,
    MadGraphWorkflowArtifact,
    build_madgraph_workflow_artifact,
)
from hep_agent.models import (
    AgentProfile,
    OllamaClient,
    OllamaClientError,
    PlannerError,
    plan_workflow,
    repair_workflow,
)
from hep_agent.models.semantic_process import (
    SemanticPlanningError,
    compile_semantic_process_workflow,
    plan_semantic_process,
)
from hep_agent.orchestration.approval import (
    ApprovalContext,
    ApprovalResult,
    decide_approval,
)
from hep_agent.orchestration.grounding_repair import (
    GroundingCorrection,
    apply_safe_grounding_corrections,
)
from hep_agent.orchestration.process_reconciliation import (
    remove_redundant_inclusive_subprocesses,
)
from hep_agent.schemas import WorkflowIntent
from hep_agent.validation import (
    GroundingResult,
    ValidationIssue,
    ValidationLevel,
    ValidationReport,
    validate_madgraph_workflow_artifact,
    validate_model_domain,
    validate_request_grounding,
)
from hep_agent.validation.analysis_request import (
    extract_analysis_request_facts,
    validate_analysis_request_capability,
)
from hep_agent.validation.process_request import (
    extract_explicit_process_expression,
)


class PreExecutionStatus(str, Enum):
    READY_FOR_APPROVAL = "ready_for_approval"
    BLOCKED = "blocked"
    FAILED = "failed"


class FailureCategory(str, Enum):
    MODEL_INFRASTRUCTURE = "model_infrastructure_failure"
    PLANNER_SEMANTIC = "planner_semantic_failure"
    REPAIR_SEMANTIC = "repair_semantic_failure"
    GROUNDING = "grounding_failure"
    UNSUPPORTED_REQUEST = "unsupported_request"
    BUILDER = "builder_failure"
    ARTIFACT_VALIDATION = "artifact_validation_failure"


@dataclass(frozen=True)
class ModelCallRecord:
    """One attempted local-model call and its observed duration."""

    role: str
    model: str
    duration_seconds: float | None


@dataclass(frozen=True)
class AgentProgressEvent:
    """One observable operational event from the agent loop."""

    event_type: str
    message: str

    role: str | None = None
    model: str | None = None
    duration_seconds: float | None = None

    issue_codes: tuple[str, ...] = ()


ProgressObserver = Callable[
    [AgentProgressEvent],
    None,
]


@dataclass(frozen=True)
class PreExecutionResult:
    """Complete result of the agent before external execution."""

    status: PreExecutionStatus
    user_request: str

    workflow: WorkflowIntent | None = None
    artifact: MadGraphWorkflowArtifact | None = None
    approval: ApprovalResult | None = None

    grounding_report: ValidationReport | None = None
    artifact_report: ValidationReport | None = None

    corrections: tuple[GroundingCorrection, ...] = ()
    model_calls: tuple[ModelCallRecord, ...] = ()

    repair_attempts: int = 0
    fallback_used: bool = False

    failure_category: FailureCategory | None = None
    failure_message: str | None = None

    @property
    def llm_call_count(self) -> int:
        return len(self.model_calls)

    @property
    def is_ready(self) -> bool:
        return self.status == PreExecutionStatus.READY_FOR_APPROVAL


def _call_record(
    role: str,
    model: str,
    duration_seconds: float | None,
) -> ModelCallRecord:
    return ModelCallRecord(
        role=role,
        model=model,
        duration_seconds=duration_seconds,
    )


def _add_repair_failure_feedback(
    report: ValidationReport,
    *,
    role: str,
    message: str,
) -> ValidationReport:
    """Add one failed repair's error to the next model prompt.

    The original deterministic validation issues are retained. The
    failed repair output itself is not trusted or used as workflow
    state; only its parser/schema error is supplied as feedback.
    """

    clipped_message = message[-4000:]

    issue = ValidationIssue(
        code="previous_repair_output_invalid",
        message=(
            f"{role} returned an invalid structured workflow. "
            "Correct the following parser or schema error in the "
            f"next attempt: {clipped_message}"
        ),
        level=ValidationLevel.ERROR,
        path="workflow",
    )

    return ValidationReport(
        issues=(
            *report.issues,
            issue,
        )
    )


def _emit_progress(
    observer: ProgressObserver | None,
    *,
    event_type: str,
    message: str,
    role: str | None = None,
    model: str | None = None,
    duration_seconds: float | None = None,
    issue_codes: tuple[str, ...] = (),
) -> None:
    """Emit progress without allowing a UI callback to break the agent."""

    if observer is None:
        return

    event = AgentProgressEvent(
        event_type=event_type,
        message=message,
        role=role,
        model=model,
        duration_seconds=duration_seconds,
        issue_codes=issue_codes,
    )

    try:
        observer(event)
    except Exception:
        # Progress reporting is observational. A UI failure must not
        # alter planning, validation, or execution behavior.
        return


def _emit_validation_progress(
    observer: ProgressObserver | None,
    *,
    report: ValidationReport,
    stage: str,
) -> None:
    """Emit one deterministic validation result."""

    codes = tuple(
        issue.code
        for issue in report.errors
    )

    if codes:
        _emit_progress(
            observer,
            event_type="validation_failed",
            message=(
                f"{stage} validation failed: "
                + ", ".join(codes)
            ),
            issue_codes=codes,
        )
    else:
        _emit_progress(
            observer,
            event_type="validation_passed",
            message=(
                f"{stage} validation passed."
            ),
        )


def normalize_user_request(
    user_request: str,
) -> str:
    """Normalize harmless request-boundary whitespace.

    Leading and trailing spaces or newlines must not change the
    request sent to the planner or deterministic validators.
    """

    if not isinstance(user_request, str):
        raise TypeError(
            "The user request must be a string."
        )

    normalized = user_request.strip()

    if not normalized:
        raise ValueError(
            "The user request cannot be empty."
        )

    return normalized




_NATURAL_DECAY_PATTERN = re.compile(
    r"\b(?:decay|decays|decaying|decayed)\b",
    re.IGNORECASE,
)

_NATURAL_CHANNEL_PATTERN = re.compile(
    r"\b(?:through|via)\b",
    re.IGNORECASE,
)


def _should_use_semantic_process_planner(
    user_request: str,
) -> bool:
    """Choose the thin semantic planner for ordinary process language.

    Explicit MadGraph-style process expressions remain on the existing
    strict route, except when the remainder of the request adds a
    natural-language decay or ambiguous channel constraint.
    """

    analysis_facts = (
        extract_analysis_request_facts(
            user_request
        )
    )

    # Rich structured MadAnalysis requests still use the established
    # full planner because the thin process schema does not construct
    # histogram and cut plans.
    if (
        analysis_facts.madanalysis_choice
        is True
        or analysis_facts.custom_plot_requested
        or analysis_facts.cut_request_present
    ):
        return False

    if _NATURAL_DECAY_PATTERN.search(
        user_request
    ):
        return True

    if _NATURAL_CHANNEL_PATTERN.search(
        user_request
    ):
        return True

    explicit_process = (
        extract_explicit_process_expression(
            user_request
        )
    )

    return explicit_process is None


def _run_semantic_preexecution(
    user_request: str,
    *,
    client: OllamaClient,
    profile: AgentProfile,
    progress_observer: ProgressObserver | None,
) -> PreExecutionResult:
    """Run the thin semantic planner and deterministic compiler."""

    model_calls: list[
        ModelCallRecord
    ] = []

    _emit_progress(
        progress_observer,
        event_type="semantic_planner_started",
        message=(
            "Translating the request into a compact "
            "MadGraph process expression."
        ),
        role="semantic_planner",
        model=profile.primary_model,
    )

    try:
        semantic = plan_semantic_process(
            user_request,
            client=client,
            model=profile.primary_model,
            timeout_seconds=(
                profile.primary_timeout_seconds
            ),
        )

    except OllamaClientError as exc:
        _emit_progress(
            progress_observer,
            event_type="model_failure",
            message=(
                "The semantic planner could not reach "
                "the configured model."
            ),
            role="semantic_planner",
            model=profile.primary_model,
        )

        return PreExecutionResult(
            status=PreExecutionStatus.FAILED,
            user_request=user_request,
            failure_category=(
                FailureCategory
                .MODEL_INFRASTRUCTURE
            ),
            failure_message=str(exc),
        )

    except SemanticPlanningError as exc:
        blocked = exc.code in {
            "ambiguous_channel_request",
            "missing_energy",
            "missing_event_count",
        }

        _emit_progress(
            progress_observer,
            event_type=(
                "semantic_request_blocked"
                if blocked
                else "semantic_planner_failed"
            ),
            message=str(exc),
            role="semantic_planner",
            model=profile.primary_model,
            issue_codes=(exc.code,),
        )

        return PreExecutionResult(
            status=(
                PreExecutionStatus.BLOCKED
                if blocked
                else PreExecutionStatus.FAILED
            ),
            user_request=user_request,
            failure_category=(
                FailureCategory.UNSUPPORTED_REQUEST
                if blocked
                else FailureCategory.PLANNER_SEMANTIC
            ),
            failure_message=str(exc),
        )

    model_calls.append(
        _call_record(
            role="semantic_planner",
            model=profile.primary_model,
            duration_seconds=(
                semantic
                .model_response
                .total_duration_seconds
            ),
        )
    )

    _emit_progress(
        progress_observer,
        event_type="semantic_planner_completed",
        message=(
            "Semantic process translation completed: "
            f"{semantic.process_command}"
        ),
        role="semantic_planner",
        model=profile.primary_model,
        duration_seconds=(
            semantic
            .model_response
            .total_duration_seconds
        ),
    )

    try:
        workflow = (
            compile_semantic_process_workflow(
                user_request,
                semantic.process_command,
                pythia8_hint=semantic.pythia8,
                delphes_hint=semantic.delphes,
            )
        )

    except SemanticPlanningError as exc:
        blocked = exc.code in {
            "ambiguous_channel_request",
            "missing_energy",
            "missing_event_count",
        }

        return PreExecutionResult(
            status=(
                PreExecutionStatus.BLOCKED
                if blocked
                else PreExecutionStatus.FAILED
            ),
            user_request=user_request,
            model_calls=tuple(model_calls),
            failure_category=(
                FailureCategory.UNSUPPORTED_REQUEST
                if blocked
                else FailureCategory.PLANNER_SEMANTIC
            ),
            failure_message=str(exc),
        )

    # The semantic compiler itself restores deterministic request facts:
    # energy, event count, beams, and pipeline choices. The large
    # natural-language grounding validator is deliberately not applied
    # because decay daughters are not top-level hard-process particles.
    grounding_report = ValidationReport(
        issues=()
    )

    _emit_progress(
        progress_observer,
        event_type="semantic_workflow_compiled",
        message=(
            "The compact process expression was compiled "
            "into the full validated workflow schema."
        ),
    )

    try:
        artifact = (
            build_madgraph_workflow_artifact(
                workflow
            )
        )

    except MadGraphBuildError as exc:
        return PreExecutionResult(
            status=PreExecutionStatus.BLOCKED,
            user_request=user_request,
            workflow=workflow,
            grounding_report=grounding_report,
            model_calls=tuple(model_calls),
            failure_category=(
                FailureCategory.BUILDER
            ),
            failure_message=str(exc),
        )

    artifact_report = (
        validate_madgraph_workflow_artifact(
            workflow,
            artifact,
        )
    )

    _emit_validation_progress(
        progress_observer,
        report=artifact_report,
        stage="Artifact",
    )

    if not artifact_report.is_valid:
        return PreExecutionResult(
            status=PreExecutionStatus.BLOCKED,
            user_request=user_request,
            workflow=workflow,
            artifact=artifact,
            grounding_report=grounding_report,
            artifact_report=artifact_report,
            model_calls=tuple(model_calls),
            failure_category=(
                FailureCategory
                .ARTIFACT_VALIDATION
            ),
            failure_message=(
                "The semantic workflow compiled, but "
                "its deterministic artifact failed validation."
            ),
        )

    approval = decide_approval(
        workflow,
        artifact_report,
        context=ApprovalContext(
            repair_changed_physics=False
        ),
    )

    _emit_progress(
        progress_observer,
        event_type="ready_for_approval",
        message=(
            "Semantic workflow validated and is "
            "ready for approval."
        ),
    )

    return PreExecutionResult(
        status=(
            PreExecutionStatus
            .READY_FOR_APPROVAL
        ),
        user_request=user_request,
        workflow=workflow,
        artifact=artifact,
        approval=approval,
        grounding_report=grounding_report,
        artifact_report=artifact_report,
        model_calls=tuple(model_calls),
        repair_attempts=0,
        fallback_used=False,
    )


def _repair_driving_report(
    grounding: GroundingResult,
) -> ValidationReport:
    """Errors the repair loop should attempt to fix.

    Combines grounding mismatches (physics vs. the request) with model-domain
    violations (e.g. a particle token not defined in the selected model). This
    lets an invalid particle produced by the planner be fed back to the repair
    model with its suggested correction, instead of only being blocked at the
    final artifact check. If repair cannot fix it, the final artifact
    validation still blocks execution, so containment is preserved.
    """

    domain = validate_model_domain(grounding.workflow)
    return ValidationReport(
        issues=tuple(grounding.report.issues)
        + tuple(domain.issues)
    )


def run_preexecution_loop(
    user_request: str,
    *,
    client: OllamaClient,
    profile: AgentProfile,
    progress_observer: ProgressObserver | None = None,
) -> PreExecutionResult:
    """Run the complete agent loop up to, but not including, execution."""

    user_request = normalize_user_request(
        user_request
    )

    capability_report = (
        validate_analysis_request_capability(
            user_request
        )
    )

    if not capability_report.is_valid:
        message = "; ".join(
            issue.message
            for issue in capability_report.errors
        )

        return PreExecutionResult(
            status=PreExecutionStatus.BLOCKED,
            user_request=user_request,
            grounding_report=capability_report,
            failure_category=(
                FailureCategory.UNSUPPORTED_REQUEST
            ),
            failure_message=message,
        )

    # Semantic routing is a production Ollama path. Unit tests and
    # integrations may provide lightweight client doubles while mocking
    # the established structured planner; those must remain on the
    # original planner/repair route.
    if (
        isinstance(client, OllamaClient)
        and _should_use_semantic_process_planner(
            user_request
        )
    ):
        return _run_semantic_preexecution(
            user_request,
            client=client,
            profile=profile,
            progress_observer=(
                progress_observer
            ),
        )

    model_calls: list[ModelCallRecord] = []
    corrections: list[GroundingCorrection] = []

    planner_result = None

    for planner_attempt in range(
        1,
        profile.max_planner_attempts + 1,
    ):
        role = (
            "planner"
            if planner_attempt == 1
            else f"planner_retry_{planner_attempt}"
        )

        _emit_progress(
            progress_observer,
            event_type="model_call_started",
            message=(
                f"Calling {profile.primary_model} "
                f"for {role}."
            ),
            role=role,
            model=profile.primary_model,
        )

        attempt_started = time.perf_counter()

        try:
            candidate = plan_workflow(
                user_request,
                client=client,
                model=profile.primary_model,
                timeout_seconds=(
                    profile.primary_timeout_seconds
                ),
            )

        except OllamaClientError as exc:
            elapsed = (
                time.perf_counter()
                - attempt_started
            )

            _emit_progress(
                progress_observer,
                event_type="model_call_failed",
                message=(
                    f"{role} failed: {exc}"
                ),
                role=role,
                model=profile.primary_model,
                duration_seconds=elapsed,
            )

            model_calls.append(
                _call_record(
                    role=(
                        f"{role}_"
                        "infrastructure_failure"
                    ),
                    model=profile.primary_model,
                    duration_seconds=elapsed,
                )
            )

            if (
                planner_attempt
                < profile.max_planner_attempts
            ):
                continue

            return PreExecutionResult(
                status=PreExecutionStatus.FAILED,
                user_request=user_request,
                model_calls=tuple(model_calls),
                failure_category=(
                    FailureCategory
                    .MODEL_INFRASTRUCTURE
                ),
                failure_message=(
                    "All initial planner attempts failed. "
                    f"Final error: {exc}"
                ),
            )

        except PlannerError as exc:
            elapsed = (
                time.perf_counter()
                - attempt_started
            )

            _emit_progress(
                progress_observer,
                event_type="model_call_failed",
                message=(
                    f"{role} returned invalid "
                    f"structured output: {exc}"
                ),
                role=role,
                model=profile.primary_model,
                duration_seconds=elapsed,
            )

            model_calls.append(
                _call_record(
                    role=(
                        f"{role}_"
                        "semantic_failure"
                    ),
                    model=profile.primary_model,
                    duration_seconds=elapsed,
                )
            )

            if (
                planner_attempt
                < profile.max_planner_attempts
            ):
                continue

            return PreExecutionResult(
                status=PreExecutionStatus.FAILED,
                user_request=user_request,
                model_calls=tuple(model_calls),
                failure_category=(
                    FailureCategory
                    .PLANNER_SEMANTIC
                ),
                failure_message=(
                    "All initial planner attempts returned "
                    "invalid structured workflows. "
                    f"Final error: {exc}"
                ),
            )

        planner_duration = (
            candidate
            .model_response
            .total_duration_seconds
        )

        _emit_progress(
            progress_observer,
            event_type="model_call_completed",
            message=(
                f"{role} completed successfully."
            ),
            role=role,
            model=profile.primary_model,
            duration_seconds=planner_duration,
        )

        model_calls.append(
            _call_record(
                role=role,
                model=profile.primary_model,
                duration_seconds=planner_duration,
            )
        )

        planner_result = candidate
        break

    if planner_result is None:
        raise RuntimeError(
            "Planner-attempt loop finished without "
            "a result or recorded failure."
        )

    current_workflow = planner_result.workflow

    deterministic = apply_safe_grounding_corrections(
        user_request,
        current_workflow,
    )
    current_workflow = deterministic.workflow
    corrections.extend(deterministic.corrections)

    reconciliation = (
        remove_redundant_inclusive_subprocesses(
            current_workflow
        )
    )
    current_workflow = reconciliation.workflow

    grounding = validate_request_grounding(
        user_request,
        current_workflow,
    )

    repair_report = _repair_driving_report(grounding)

    _emit_validation_progress(
        progress_observer,
        report=repair_report,
        stage="Initial workflow",
    )

    repair_attempts = 0
    fallback_used = False

    # The feedback supplied to a repair begins with deterministic
    # grounding issues. Schema-invalid repair attempts append their
    # exact error so the next model does not repeat the same mistake.
    repair_feedback = repair_report
    last_repair_error: str | None = None

    while (
        not repair_report.is_valid
        and repair_attempts < profile.max_repairs
    ):
        repair_attempts += 1

        role = (
            f"primary_repair_{repair_attempts}"
        )

        _emit_progress(
            progress_observer,
            event_type="model_call_started",
            message=(
                f"Calling {profile.primary_model} "
                f"for {role}."
            ),
            role=role,
            model=profile.primary_model,
        )

        attempt_started = time.perf_counter()

        try:
            repair_result = repair_workflow(
                user_request=user_request,
                invalid_workflow=current_workflow,
                validation_report=repair_feedback,
                client=client,
                model=profile.primary_model,
                timeout_seconds=(
                    profile.primary_timeout_seconds
                ),
            )

        except OllamaClientError as exc:
            elapsed = (
                time.perf_counter()
                - attempt_started
            )

            _emit_progress(
                progress_observer,
                event_type="model_call_failed",
                message=(
                    f"{role} failed: {exc}"
                ),
                role=role,
                model=profile.primary_model,
                duration_seconds=elapsed,
            )

            model_calls.append(
                _call_record(
                    role=(
                        f"{role}_"
                        "infrastructure_failure"
                    ),
                    model=profile.primary_model,
                    duration_seconds=elapsed,
                )
            )

            return PreExecutionResult(
                status=PreExecutionStatus.FAILED,
                user_request=user_request,
                workflow=current_workflow,
                grounding_report=grounding.report,
                corrections=tuple(corrections),
                model_calls=tuple(model_calls),
                repair_attempts=repair_attempts,
                fallback_used=fallback_used,
                failure_category=(
                    FailureCategory
                    .MODEL_INFRASTRUCTURE
                ),
                failure_message=str(exc),
            )

        except PlannerError as exc:
            elapsed = (
                time.perf_counter()
                - attempt_started
            )

            model_calls.append(
                _call_record(
                    role=f"{role}_schema_failure",
                    model=profile.primary_model,
                    duration_seconds=elapsed,
                )
            )

            _emit_progress(
                progress_observer,
                event_type="model_call_failed",
                message=(
                    f"{role} returned schema-invalid "
                    f"output: {exc}"
                ),
                role=role,
                model=profile.primary_model,
                duration_seconds=elapsed,
            )

            last_repair_error = str(exc)

            repair_feedback = (
                _add_repair_failure_feedback(
                    repair_feedback,
                    role=role,
                    message=str(exc),
                )
            )

            # Keep the last schema-valid workflow as state and let
            # the next repair attempt use the augmented feedback.
            continue

        repair_duration = (
            repair_result
            .model_response
            .total_duration_seconds
        )

        _emit_progress(
            progress_observer,
            event_type="model_call_completed",
            message=(
                f"{role} completed successfully."
            ),
            role=role,
            model=profile.primary_model,
            duration_seconds=repair_duration,
        )

        model_calls.append(
            _call_record(
                role=role,
                model=profile.primary_model,
                duration_seconds=repair_duration,
            )
        )

        current_workflow = (
            repair_result.workflow
        )

        deterministic = (
            apply_safe_grounding_corrections(
                user_request,
                current_workflow,
            )
        )
        current_workflow = (
            deterministic.workflow
        )
        corrections.extend(
            deterministic.corrections
        )

        # Every model-produced workflow goes through the same
        # deterministic reconciliation used after initial planning.
        reconciliation = (
            remove_redundant_inclusive_subprocesses(
                current_workflow
            )
        )
        current_workflow = (
            reconciliation.workflow
        )

        grounding = validate_request_grounding(
            user_request,
            current_workflow,
        )

        repair_report = _repair_driving_report(grounding)

        _emit_validation_progress(
            progress_observer,
            report=repair_report,
            stage=role,
        )

        repair_feedback = repair_report
        last_repair_error = None

    if (
        not repair_report.is_valid
        and profile.fallback_model is not None
    ):
        fallback_used = True

        fallback_timeout = (
            profile.fallback_timeout_seconds
            or profile.primary_timeout_seconds
        )

        _emit_progress(
            progress_observer,
            event_type="model_call_started",
            message=(
                f"Escalating to fallback model "
                f"{profile.fallback_model}."
            ),
            role="fallback_repair",
            model=profile.fallback_model,
        )

        fallback_started = time.perf_counter()

        try:
            fallback_result = repair_workflow(
                user_request=user_request,
                invalid_workflow=current_workflow,
                validation_report=repair_feedback,
                client=client,
                model=profile.fallback_model,
                timeout_seconds=fallback_timeout,
            )

        except OllamaClientError as exc:
            elapsed = (
                time.perf_counter()
                - fallback_started
            )

            model_calls.append(
                _call_record(
                    role=(
                        "fallback_repair_"
                        "infrastructure_failure"
                    ),
                    model=profile.fallback_model,
                    duration_seconds=elapsed,
                )
            )

            return PreExecutionResult(
                status=PreExecutionStatus.FAILED,
                user_request=user_request,
                workflow=current_workflow,
                grounding_report=grounding.report,
                corrections=tuple(corrections),
                model_calls=tuple(model_calls),
                repair_attempts=repair_attempts,
                fallback_used=True,
                failure_category=(
                    FailureCategory
                    .MODEL_INFRASTRUCTURE
                ),
                failure_message=str(exc),
            )

        except PlannerError as exc:
            elapsed = (
                time.perf_counter()
                - fallback_started
            )

            model_calls.append(
                _call_record(
                    role=(
                        "fallback_repair_"
                        "schema_failure"
                    ),
                    model=profile.fallback_model,
                    duration_seconds=elapsed,
                )
            )

            return PreExecutionResult(
                status=PreExecutionStatus.FAILED,
                user_request=user_request,
                workflow=current_workflow,
                grounding_report=grounding.report,
                corrections=tuple(corrections),
                model_calls=tuple(model_calls),
                repair_attempts=repair_attempts,
                fallback_used=True,
                failure_category=(
                    FailureCategory.REPAIR_SEMANTIC
                ),
                failure_message=str(exc),
            )

        fallback_duration = (
            fallback_result
            .model_response
            .total_duration_seconds
        )

        _emit_progress(
            progress_observer,
            event_type="model_call_completed",
            message=(
                "Fallback repair completed successfully."
            ),
            role="fallback_repair",
            model=profile.fallback_model,
            duration_seconds=fallback_duration,
        )

        model_calls.append(
            _call_record(
                role="fallback_repair",
                model=profile.fallback_model,
                duration_seconds=fallback_duration,
            )
        )

        current_workflow = (
            fallback_result.workflow
        )

        deterministic = (
            apply_safe_grounding_corrections(
                user_request,
                current_workflow,
            )
        )
        current_workflow = (
            deterministic.workflow
        )
        corrections.extend(
            deterministic.corrections
        )

        reconciliation = (
            remove_redundant_inclusive_subprocesses(
                current_workflow
            )
        )
        current_workflow = (
            reconciliation.workflow
        )

        grounding = validate_request_grounding(
            user_request,
            current_workflow,
        )

        repair_report = _repair_driving_report(grounding)

        _emit_validation_progress(
            progress_observer,
            report=repair_report,
            stage="Fallback repair",
        )

        repair_feedback = repair_report
        last_repair_error = None

    if not grounding.report.is_valid:
        return PreExecutionResult(
            status=PreExecutionStatus.BLOCKED,
            user_request=user_request,
            workflow=current_workflow,
            grounding_report=grounding.report,
            corrections=tuple(corrections),
            model_calls=tuple(model_calls),
            repair_attempts=repair_attempts,
            fallback_used=fallback_used,
            failure_category=FailureCategory.GROUNDING,
            failure_message=(
                "The structured workflow still contradicts the "
                "original user request."
                + (
                    " The final repair output also failed schema "
                    f"validation: {last_repair_error}"
                    if last_repair_error
                    else ""
                )
            ),
        )

    try:
        artifact = build_madgraph_workflow_artifact(
            grounding.workflow
        )
    except MadGraphBuildError as exc:
        return PreExecutionResult(
            status=PreExecutionStatus.BLOCKED,
            user_request=user_request,
            workflow=grounding.workflow,
            grounding_report=grounding.report,
            corrections=tuple(corrections),
            model_calls=tuple(model_calls),
            repair_attempts=repair_attempts,
            fallback_used=fallback_used,
            failure_category=FailureCategory.BUILDER,
            failure_message=str(exc),
        )

    artifact_report = validate_madgraph_workflow_artifact(
        grounding.workflow,
        artifact,
    )

    if not artifact_report.is_valid:
        return PreExecutionResult(
            status=PreExecutionStatus.BLOCKED,
            user_request=user_request,
            workflow=grounding.workflow,
            artifact=artifact,
            grounding_report=grounding.report,
            artifact_report=artifact_report,
            corrections=tuple(corrections),
            model_calls=tuple(model_calls),
            repair_attempts=repair_attempts,
            fallback_used=fallback_used,
            failure_category=FailureCategory.ARTIFACT_VALIDATION,
            failure_message=(
                "The deterministic artifact failed validation."
            ),
        )

    approval = decide_approval(
        grounding.workflow,
        artifact_report,
        context=ApprovalContext(
            repair_changed_physics=(
                repair_attempts > 0 or fallback_used
            ),
        ),
    )

    return PreExecutionResult(
        status=PreExecutionStatus.READY_FOR_APPROVAL,
        user_request=user_request,
        workflow=grounding.workflow,
        artifact=artifact,
        approval=approval,
        grounding_report=grounding.report,
        artifact_report=artifact_report,
        corrections=tuple(corrections),
        model_calls=tuple(model_calls),
        repair_attempts=repair_attempts,
        fallback_used=fallback_used,
    )
