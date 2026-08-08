"""Deterministic validation for collider workflows and artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from hep_agent.builders import (
    MadGraphArtifact,
    MadGraphBuildError,
    build_madgraph_artifact,
)
from hep_agent.schemas import (
    CouplingComparison,
    ModelSource,
    TaskType,
    WorkflowIntent,
)


SAFE_PARTICLE_RE = re.compile(r"^[A-Za-z0-9_+\-~]+$")
SAFE_MODEL_RE = re.compile(r"^[A-Za-z0-9_+\-./]+$")
SAFE_OUTPUT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


class ValidationLevel(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    """One deterministic validation result."""

    code: str
    message: str
    level: ValidationLevel
    path: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    """Complete validation result."""

    issues: tuple[ValidationIssue, ...]

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(
            issue
            for issue in self.issues
            if issue.level == ValidationLevel.ERROR
        )

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(
            issue
            for issue in self.issues
            if issue.level == ValidationLevel.WARNING
        )

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _safe_particle_name(name: str) -> bool:
    return bool(SAFE_PARTICLE_RE.fullmatch(name))


def validate_workflow(workflow: WorkflowIntent) -> ValidationReport:
    """Validate structured physics intent before artifact construction."""

    issues: list[ValidationIssue] = []

    if workflow.task_type in {
        TaskType.GENERATE_PROCESS,
        TaskType.RUN_SIMULATION,
    }:
        if not workflow.pipeline.madgraph:
            issues.append(
                ValidationIssue(
                    code="madgraph_required",
                    message=(
                        "Process generation and simulation require the "
                        "MadGraph pipeline stage."
                    ),
                    level=ValidationLevel.ERROR,
                    path="pipeline.madgraph",
                )
            )

    if workflow.pipeline.delphes and not workflow.pipeline.pythia8:
        issues.append(
            ValidationIssue(
                code="delphes_requires_pythia",
                message=(
                    "The current workflow requires Pythia8 before "
                    "Delphes."
                ),
                level=ValidationLevel.ERROR,
                path="pipeline.delphes",
            )
        )

    if not SAFE_MODEL_RE.fullmatch(workflow.model.name):
        issues.append(
            ValidationIssue(
                code="unsafe_model_name",
                message="The model name contains unsafe characters.",
                level=ValidationLevel.ERROR,
                path="model.name",
            )
        )

    if (
        workflow.model.source == ModelSource.USER_UFO
        and not workflow.model.model_path
    ):
        issues.append(
            ValidationIssue(
                code="missing_ufo_path",
                message="A user UFO model requires a model path.",
                level=ValidationLevel.ERROR,
                path="model.model_path",
            )
        )

    if workflow.run.output_name:
        if not SAFE_OUTPUT_RE.fullmatch(workflow.run.output_name):
            issues.append(
                ValidationIssue(
                    code="unsafe_output_name",
                    message=(
                        "The output name must contain only letters, "
                        "numbers, dots, underscores, and hyphens."
                    ),
                    level=ValidationLevel.ERROR,
                    path="run.output_name",
                )
            )

    if workflow.run.nevents > 100_000:
        issues.append(
            ValidationIssue(
                code="large_event_count",
                message=(
                    "The requested event count is above the default "
                    "automatic-execution limit."
                ),
                level=ValidationLevel.WARNING,
                path="run.nevents",
            )
        )

    for process_index, process in enumerate(workflow.processes):
        base_path = f"processes[{process_index}]"

        if len(process.required_intermediates) > 1:
            issues.append(
                ValidationIssue(
                    code="multiple_required_intermediates",
                    message=(
                        "Schema version 1 safely supports only one "
                        "required intermediate particle."
                    ),
                    level=ValidationLevel.ERROR,
                    path=f"{base_path}.required_intermediates",
                )
            )

        particle_names: list[tuple[str, str]] = []

        for index, name in enumerate(process.incoming_particles):
            particle_names.append(
                (name, f"{base_path}.incoming_particles[{index}]")
            )

        for index, node in enumerate(process.final_particles):
            for nested_node in node.walk():
                particle_names.append(
                    (
                        nested_node.particle,
                        f"{base_path}.final_particles[{index}]",
                    )
                )

        for index, name in enumerate(process.required_intermediates):
            particle_names.append(
                (
                    name,
                    f"{base_path}.required_intermediates[{index}]",
                )
            )

        for index, name in enumerate(process.excluded_particles):
            particle_names.append(
                (
                    name,
                    f"{base_path}.excluded_particles[{index}]",
                )
            )

        for particle_name, path in particle_names:
            if not _safe_particle_name(particle_name):
                issues.append(
                    ValidationIssue(
                        code="unsafe_particle_name",
                        message=(
                            f"Particle name {particle_name!r} contains "
                            "unsupported or unsafe characters."
                        ),
                        level=ValidationLevel.ERROR,
                        path=path,
                    )
                )

        for coupling_name, coupling in process.coupling_orders.items():
            if not coupling_name.isalnum():
                issues.append(
                    ValidationIssue(
                        code="unsafe_coupling_name",
                        message=(
                            f"Coupling name {coupling_name!r} contains "
                            "unsupported characters."
                        ),
                        level=ValidationLevel.ERROR,
                        path=f"{base_path}.coupling_orders",
                    )
                )

            if coupling.comparison == CouplingComparison.MINIMUM:
                issues.append(
                    ValidationIssue(
                        code="unsupported_minimum_coupling",
                        message=(
                            "Minimum coupling-order restrictions are "
                            "not yet supported safely."
                        ),
                        level=ValidationLevel.ERROR,
                        path=(
                            f"{base_path}.coupling_orders."
                            f"{coupling_name}"
                        ),
                    )
                )

    # Model-relative domain validation: reject particle or multiparticle
    # tokens that do not exist in the selected model before any artifact is
    # built or executed. Imported locally to avoid an import cycle at module
    # load time (model_domain imports the issue types from this module).
    from hep_agent.validation.model_domain import validate_model_domain

    issues.extend(validate_model_domain(workflow).issues)

    try:
        build_madgraph_artifact(workflow)
    except MadGraphBuildError as exc:
        issues.append(
            ValidationIssue(
                code="builder_rejected_workflow",
                message=str(exc),
                level=ValidationLevel.ERROR,
                path="processes",
            )
        )

    return ValidationReport(issues=tuple(issues))


def validate_madgraph_artifact(
    workflow: WorkflowIntent,
    artifact: MadGraphArtifact,
) -> ValidationReport:
    """Check that an artifact is safe and matches deterministic output."""

    issues: list[ValidationIssue] = []

    workflow_report = validate_workflow(workflow)
    issues.extend(workflow_report.issues)

    if workflow_report.errors:
        return ValidationReport(issues=tuple(issues))

    try:
        expected = build_madgraph_artifact(workflow)
    except MadGraphBuildError as exc:
        issues.append(
            ValidationIssue(
                code="artifact_rebuild_failed",
                message=str(exc),
                level=ValidationLevel.ERROR,
                path="artifact",
            )
        )
        return ValidationReport(issues=tuple(issues))

    if artifact.commands != expected.commands:
        issues.append(
            ValidationIssue(
                code="artifact_mismatch",
                message=(
                    "The artifact does not match the deterministic "
                    "builder output."
                ),
                level=ValidationLevel.ERROR,
                path="artifact.commands",
            )
        )

    allowed_prefixes = (
        "import model ",
        "generate ",
        "add process ",
        "output ",
    )

    for index, command in enumerate(artifact.commands):
        if "\n" in command or "\r" in command or ";" in command:
            issues.append(
                ValidationIssue(
                    code="unsafe_command_content",
                    message=(
                        "A generated command contains a newline, "
                        "carriage return, or semicolon."
                    ),
                    level=ValidationLevel.ERROR,
                    path=f"artifact.commands[{index}]",
                )
            )

        if not command.startswith(allowed_prefixes):
            issues.append(
                ValidationIssue(
                    code="unsupported_command",
                    message=f"Unsupported command: {command!r}.",
                    level=ValidationLevel.ERROR,
                    path=f"artifact.commands[{index}]",
                )
            )

    generate_count = sum(
        command.startswith("generate ")
        for command in artifact.commands
    )

    if generate_count != 1:
        issues.append(
            ValidationIssue(
                code="invalid_generate_count",
                message="The artifact must contain exactly one generate command.",
                level=ValidationLevel.ERROR,
                path="artifact.commands",
            )
        )

    if not artifact.commands:
        issues.append(
            ValidationIssue(
                code="empty_artifact",
                message="The generated artifact is empty.",
                level=ValidationLevel.ERROR,
                path="artifact.commands",
            )
        )
    elif not artifact.commands[-1].startswith("output "):
        issues.append(
            ValidationIssue(
                code="missing_final_output",
                message="The final command must be an output command.",
                level=ValidationLevel.ERROR,
                path="artifact.commands",
            )
        )

    return ValidationReport(issues=tuple(issues))
