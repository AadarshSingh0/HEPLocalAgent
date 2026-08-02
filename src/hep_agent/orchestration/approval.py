"""Approval policy for validated collider workflows.

This module decides whether a workflow may automatically continue,
requires explicit human confirmation, or must be blocked.

It does not sleep, display a user interface, or execute any tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from hep_agent.schemas import FieldSource, WorkflowIntent
from hep_agent.validation import ValidationReport


class ApprovalDecision(str, Enum):
    AUTO_CONFIRM = "auto_confirm"
    EXPLICIT_CONFIRMATION = "explicit_confirmation_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ApprovalContext:
    """Additional information known by the orchestrator."""

    ambiguous_request: bool = False
    repair_changed_physics: bool = False
    overwrite_risk: bool = False
    unsupported_feature_requested: bool = False


@dataclass(frozen=True)
class ApprovalResult:
    """Final approval decision returned to the UI or CLI."""

    decision: ApprovalDecision
    reasons: tuple[str, ...] = field(default_factory=tuple)
    auto_confirm_delay_seconds: int | None = None

    @property
    def may_execute(self) -> bool:
        return self.decision != ApprovalDecision.BLOCKED


PHYSICS_CRITICAL_PREFIXES = (
    "model",
    "collider",
    "processes",
)


def _has_physics_critical_model_inference(
    workflow: WorkflowIntent,
) -> bool:
    """Check whether the LLM guessed a physics-critical value."""

    for path, source in workflow.field_sources.items():
        if source != FieldSource.MODEL_INFERENCE:
            continue

        if path.startswith(PHYSICS_CRITICAL_PREFIXES):
            return True

    return False


def decide_approval(
    workflow: WorkflowIntent,
    validation_report: ValidationReport,
    *,
    context: ApprovalContext | None = None,
    auto_confirm_delay_seconds: int = 5,
) -> ApprovalResult:
    """Choose automatic, explicit, or blocked approval."""

    if auto_confirm_delay_seconds < 0:
        raise ValueError(
            "auto_confirm_delay_seconds cannot be negative."
        )

    context = context or ApprovalContext()

    if validation_report.errors:
        return ApprovalResult(
            decision=ApprovalDecision.BLOCKED,
            reasons=tuple(
                issue.message for issue in validation_report.errors
            ),
        )

    reasons: list[str] = []

    if validation_report.warnings:
        reasons.extend(
            issue.message for issue in validation_report.warnings
        )

    if context.ambiguous_request:
        reasons.append(
            "The original request contains unresolved ambiguity."
        )

    if context.repair_changed_physics:
        reasons.append(
            "A repair changed the requested physics interpretation."
        )

    if context.overwrite_risk:
        reasons.append(
            "Execution may overwrite an existing output directory."
        )

    if context.unsupported_feature_requested:
        reasons.append(
            "The request contains a feature that is not yet supported "
            "safely."
        )

    if _has_physics_critical_model_inference(workflow):
        reasons.append(
            "The planner inferred a physics-critical value that was "
            "not explicitly supplied by the user."
        )

    if reasons:
        return ApprovalResult(
            decision=ApprovalDecision.EXPLICIT_CONFIRMATION,
            reasons=tuple(reasons),
        )

    return ApprovalResult(
        decision=ApprovalDecision.AUTO_CONFIRM,
        reasons=(
            "The workflow passed validation without unresolved "
            "physics ambiguity.",
        ),
        auto_confirm_delay_seconds=auto_confirm_delay_seconds,
    )
