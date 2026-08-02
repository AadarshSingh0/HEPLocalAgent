"""Validation of complete deterministic MG5 workflows."""

from __future__ import annotations

from hep_agent.builders import (
    MadGraphBuildError,
    MadGraphWorkflowArtifact,
    build_madgraph_workflow_artifact,
)
from hep_agent.schemas import WorkflowIntent
from hep_agent.validation.core import (
    ValidationIssue,
    ValidationLevel,
    ValidationReport,
    validate_workflow,
)


def validate_madgraph_workflow_artifact(
    workflow: WorkflowIntent,
    artifact: MadGraphWorkflowArtifact,
) -> ValidationReport:
    """Validate a complete process-generation and launch artifact."""

    issues: list[ValidationIssue] = []

    workflow_report = validate_workflow(workflow)
    issues.extend(workflow_report.issues)

    if workflow_report.errors:
        return ValidationReport(issues=tuple(issues))

    try:
        expected = build_madgraph_workflow_artifact(workflow)
    except MadGraphBuildError as exc:
        issues.append(
            ValidationIssue(
                code="workflow_builder_rejected",
                message=str(exc),
                level=ValidationLevel.ERROR,
                path="workflow",
            )
        )
        return ValidationReport(issues=tuple(issues))

    if artifact.commands != expected.commands:
        issues.append(
            ValidationIssue(
                code="workflow_artifact_mismatch",
                message=(
                    "The complete MG5 artifact does not match the "
                    "deterministic builder output."
                ),
                level=ValidationLevel.ERROR,
                path="artifact.commands",
            )
        )

    for index, command in enumerate(artifact.commands):
        if "\n" in command or "\r" in command or ";" in command:
            issues.append(
                ValidationIssue(
                    code="unsafe_workflow_command",
                    message=(
                        "A workflow command contains a newline, "
                        "carriage return, or semicolon."
                    ),
                    level=ValidationLevel.ERROR,
                    path=f"artifact.commands[{index}]",
                )
            )

    launch_count = sum(
        command.startswith("launch ")
        for command in artifact.commands
    )

    done_count = sum(
        command == "done"
        for command in artifact.commands
    )

    if launch_count != 1:
        issues.append(
            ValidationIssue(
                code="invalid_launch_count",
                message=(
                    "The workflow must contain exactly one launch "
                    "command."
                ),
                level=ValidationLevel.ERROR,
                path="artifact.commands",
            )
        )

    if done_count != 1:
        issues.append(
            ValidationIssue(
                code="invalid_done_count",
                message=(
                    "The workflow must contain exactly one final done "
                    "command."
                ),
                level=ValidationLevel.ERROR,
                path="artifact.commands",
            )
        )

    if not artifact.commands or artifact.commands[-1] != "done":
        issues.append(
            ValidationIssue(
                code="missing_final_done",
                message=(
                    "The complete MG5 workflow must finish with done."
                ),
                level=ValidationLevel.ERROR,
                path="artifact.commands",
            )
        )

    return ValidationReport(issues=tuple(issues))
