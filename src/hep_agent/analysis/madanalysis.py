"""Deterministic MadAnalysis 5 script construction.

This module converts a validated HEP workflow and an existing event
file into a restricted MadAnalysis 5 script.

It does not execute MA5 and does not call an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from hep_agent.schemas import WorkflowIntent


class MadAnalysisBuildError(ValueError):
    """Raised when a safe MA5 script cannot be constructed."""


class MadAnalysisLevel(str, Enum):
    """Supported MadAnalysis event-description levels."""

    PARTON = "parton"
    HADRON = "hadron"
    RECONSTRUCTED = "reconstructed"


MODE_FLAGS = {
    MadAnalysisLevel.PARTON: "-P",
    MadAnalysisLevel.HADRON: "-H",
    MadAnalysisLevel.RECONSTRUCTED: "-R",
}


# Initial allowlist of stable final-state particles whose MA5 labels
# have the same spelling as their MadGraph labels.
SUPPORTED_PARTICLE_LABELS = {
    "e+",
    "e-",
    "mu+",
    "mu-",
    "ta+",
    "ta-",
    "a",
}


@dataclass(frozen=True)
class MadAnalysisArtifact:
    """A complete deterministic MA5 normal-mode script."""

    level: MadAnalysisLevel
    input_file: Path
    job_directory: Path
    commands: tuple[str, ...]
    expected_plot_count: int
    expected_cut_count: int = 0

    @property
    def mode_flag(self) -> str:
        """Return the MA5 command-line mode flag."""

        return MODE_FLAGS[self.level]

    @property
    def text(self) -> str:
        """Return a file-ready MA5 script."""

        return "\n".join(self.commands) + "\n"


@dataclass(frozen=True)
class MadAnalysisValidationIssue:
    """One deterministic MA5 artifact-validation issue."""

    code: str
    message: str


@dataclass(frozen=True)
class MadAnalysisValidationReport:
    """Validation report for one MA5 script artifact."""

    issues: tuple[MadAnalysisValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


def _safe_path(path: str | Path, *, label: str) -> Path:
    """Validate and normalize a filesystem path."""

    raw = str(path)

    if not raw.strip():
        raise MadAnalysisBuildError(
            f"{label} cannot be empty."
        )

    forbidden = {"\n", "\r", ";", "`"}

    if any(character in raw for character in forbidden):
        raise MadAnalysisBuildError(
            f"{label} contains an unsafe character."
        )

    return Path(path).expanduser().resolve()


def _supported_final_particles(
    workflow: WorkflowIntent,
) -> tuple[str, ...]:
    """Return unique supported top-level final-state particles."""

    particles: list[str] = []

    for process in workflow.processes:
        for node in process.final_particles:
            particle = node.particle

            if particle not in SUPPORTED_PARTICLE_LABELS:
                continue

            if particle not in particles:
                particles.append(particle)

    return tuple(particles)


def _build_process_aware_plots(
    workflow: WorkflowIntent,
) -> tuple[str, ...]:
    """Build a conservative process-aware quick-look plot set."""

    particles = _supported_final_particles(workflow)

    if not particles:
        raise MadAnalysisBuildError(
            "The current MA5 quick-look preset does not yet support "
            "any top-level final-state particle in this workflow."
        )

    commands: list[str] = []

    for particle in particles:
        commands.append(
            f"plot PT({particle}[1]) 40 0 400"
        )
        commands.append(
            f"plot ETA({particle}[1]) 40 -4 4"
        )

    # For a two-particle final state, add its invariant mass.
    if len(particles) == 2:
        commands.append(
            f"plot M({particles[0]} {particles[1]}) "
            "50 0 500"
        )

    commands.append("plot MET 40 0 400")

    return tuple(commands)


def build_madanalysis_quicklook(
    workflow: WorkflowIntent,
    *,
    input_file: str | Path,
    job_directory: str | Path,
    level: MadAnalysisLevel,
) -> MadAnalysisArtifact:
    """Build a restricted process-aware MA5 quick-look script."""

    event_file = _safe_path(
        input_file,
        label="MadAnalysis input file",
    )
    job_dir = _safe_path(
        job_directory,
        label="MadAnalysis job directory",
    )

    plots = _build_process_aware_plots(workflow)

    commands = (
        f"import {event_file} as sample",
        *plots,
        f"submit {job_dir}",
        "quit",
    )

    artifact = MadAnalysisArtifact(
        level=level,
        input_file=event_file,
        job_directory=job_dir,
        commands=commands,
        expected_plot_count=len(plots),
    )

    report = validate_madanalysis_artifact(
        artifact
    )

    if not report.is_valid:
        messages = "; ".join(
            issue.message
            for issue in report.issues
        )

        raise MadAnalysisBuildError(messages)

    return artifact


def validate_madanalysis_artifact(
    artifact: MadAnalysisArtifact,
) -> MadAnalysisValidationReport:
    """Validate a deterministic MA5 normal-mode artifact."""

    issues: list[MadAnalysisValidationIssue] = []
    commands = artifact.commands

    if not commands:
        issues.append(
            MadAnalysisValidationIssue(
                code="empty_script",
                message="The MA5 script is empty.",
            )
        )

        return MadAnalysisValidationReport(
            issues=tuple(issues)
        )

    if commands[0] != (
        f"import {artifact.input_file} as sample"
    ):
        issues.append(
            MadAnalysisValidationIssue(
                code="invalid_import",
                message=(
                    "The first MA5 command must import the "
                    "selected event file as dataset 'sample'."
                ),
            )
        )

    if commands[-1] != "quit":
        issues.append(
            MadAnalysisValidationIssue(
                code="missing_quit",
                message=(
                    "The MA5 script must end with quit."
                ),
            )
        )

    expected_submit = (
        f"submit {artifact.job_directory}"
    )

    submit_commands = [
        command
        for command in commands
        if command.startswith("submit ")
    ]

    if submit_commands != [expected_submit]:
        issues.append(
            MadAnalysisValidationIssue(
                code="invalid_submit",
                message=(
                    "The MA5 script must contain exactly one "
                    "submit command for the selected job directory."
                ),
            )
        )

    plot_commands = [
        command
        for command in commands
        if command.startswith("plot ")
    ]

    if len(plot_commands) != artifact.expected_plot_count:
        issues.append(
            MadAnalysisValidationIssue(
                code="plot_count_mismatch",
                message=(
                    "The number of MA5 plot commands does not "
                    "match the artifact metadata."
                ),
            )
        )

    cut_commands = [
        command
        for command in commands
        if command.startswith("select ")
    ]

    if len(cut_commands) != artifact.expected_cut_count:
        issues.append(
            MadAnalysisValidationIssue(
                code="cut_count_mismatch",
                message=(
                    "The number of MA5 select commands does not "
                    "match the artifact metadata."
                ),
            )
        )

    allowed_prefixes = (
        "import ",
        "select ",
        "plot ",
        "submit ",
        "quit",
    )

    for command in commands:
        if not command.startswith(allowed_prefixes):
            issues.append(
                MadAnalysisValidationIssue(
                    code="unsupported_command",
                    message=(
                        "Unsupported MA5 command: "
                        f"{command!r}"
                    ),
                )
            )

        if any(
            character in command
            for character in ("\n", "\r", ";", "`")
        ):
            issues.append(
                MadAnalysisValidationIssue(
                    code="unsafe_command",
                    message=(
                        "Unsafe character found in MA5 command: "
                        f"{command!r}"
                    ),
                )
            )

    return MadAnalysisValidationReport(
        issues=tuple(issues)
    )


# ---------------------------------------------------------------------
# Structured-analysis compiler
# ---------------------------------------------------------------------

from hep_agent.schemas.analysis import (
    AnalysisComparison,
    AnalysisCutSpec,
    AnalysisHistogramSpec,
    AnalysisObjectRef,
    AnalysisObservable,
    AnalysisPlan,
)


_OBSERVABLE_NAMES = {
    AnalysisObservable.PT: "PT",
    AnalysisObservable.ETA: "ETA",
    AnalysisObservable.ABS_ETA: "ABSETA",
    AnalysisObservable.PHI: "PHI",
    AnalysisObservable.ENERGY: "E",
    AnalysisObservable.INVARIANT_MASS: "M",
    AnalysisObservable.MET: "MET",
    AnalysisObservable.DELTA_R: "DELTAR",
    AnalysisObservable.DELTA_PHI: "DPHI_0_PI",
}


def _format_ma5_number(
    value: int | float,
) -> str:
    """Format deterministic finite numerical MA5 values."""

    return format(value, ".15g")


def _available_analysis_particles(
    workflow: WorkflowIntent,
) -> set[str]:
    """Return supported particles present anywhere in decay trees."""

    available: set[str] = set()

    for process in workflow.processes:
        for top_level in process.final_particles:
            for node in top_level.walk():
                if (
                    node.particle
                    in SUPPORTED_PARTICLE_LABELS
                ):
                    available.add(
                        node.particle
                    )

    return available


def _compile_object_reference(
    reference: AnalysisObjectRef,
    *,
    available_particles: set[str],
) -> str:
    """Compile one validated ranked particle reference."""

    if (
        reference.particle
        not in SUPPORTED_PARTICLE_LABELS
    ):
        raise MadAnalysisBuildError(
            "Structured analysis does not yet support "
            f"particle label {reference.particle!r}."
        )

    if (
        reference.particle
        not in available_particles
    ):
        raise MadAnalysisBuildError(
            f"Particle {reference.particle!r} is not "
            "present in the workflow final-state or "
            "decay structure."
        )

    return (
        f"{reference.particle}"
        f"[{reference.rank}]"
    )


def _compile_analysis_expression(
    specification: (
        AnalysisHistogramSpec
        | AnalysisCutSpec
    ),
    *,
    available_particles: set[str],
) -> str:
    """Compile one schema-validated observable expression."""

    observable = specification.observable
    ma5_name = _OBSERVABLE_NAMES[
        observable
    ]

    if observable == AnalysisObservable.MET:
        return ma5_name

    objects = [
        _compile_object_reference(
            reference,
            available_particles=(
                available_particles
            ),
        )
        for reference in specification.objects
    ]

    if observable in {
        AnalysisObservable.DELTA_R,
        AnalysisObservable.DELTA_PHI,
    }:
        return (
            f"{ma5_name}("
            f"{objects[0]},{objects[1]}"
            ")"
        )

    return (
        f"{ma5_name}("
        + " ".join(objects)
        + ")"
    )


def _compile_analysis_cut(
    cut: AnalysisCutSpec,
    *,
    available_particles: set[str],
) -> str:
    """Compile one structured cut into MA5 normal-mode syntax."""

    expression = (
        _compile_analysis_expression(
            cut,
            available_particles=(
                available_particles
            ),
        )
    )

    comparison = (
        cut.comparison.value
    )

    return (
        f"select {expression} "
        f"{comparison} "
        f"{_format_ma5_number(cut.value)}"
    )


def _compile_analysis_histogram(
    histogram: AnalysisHistogramSpec,
    *,
    available_particles: set[str],
) -> str:
    """Compile one structured histogram."""

    expression = (
        _compile_analysis_expression(
            histogram,
            available_particles=(
                available_particles
            ),
        )
    )

    return (
        f"plot {expression} "
        f"{histogram.bins} "
        f"{_format_ma5_number(histogram.minimum)} "
        f"{_format_ma5_number(histogram.maximum)}"
    )


def compile_madanalysis_quicklook_commands(
    workflow: WorkflowIntent,
) -> tuple[str, ...]:
    """Compile the deterministic quick-look analysis body.

    The returned commands exclude the run-specific import, submit,
    and quit commands whose paths are selected after event generation.
    """

    return _build_process_aware_plots(
        workflow
    )


def compile_madanalysis_plan_commands(
    workflow: WorkflowIntent,
    plan: AnalysisPlan,
) -> tuple[str, ...]:
    """Compile a structured plan into deterministic MA5 commands.

    Cuts are returned first because they are applied before every
    requested histogram. No filesystem paths or arbitrary commands
    are accepted through this interface.
    """

    available_particles = (
        _available_analysis_particles(
            workflow
        )
    )

    cuts = tuple(
        _compile_analysis_cut(
            cut,
            available_particles=(
                available_particles
            ),
        )
        for cut in plan.cuts
    )

    plots = tuple(
        _compile_analysis_histogram(
            histogram,
            available_particles=(
                available_particles
            ),
        )
        for histogram in plan.histograms
    )

    return (
        *cuts,
        *plots,
    )


def build_madanalysis_from_plan(
    workflow: WorkflowIntent,
    plan: AnalysisPlan,
    *,
    input_file: str | Path,
    job_directory: str | Path,
    level: MadAnalysisLevel,
) -> MadAnalysisArtifact:
    """Compile a structured plan into a restricted MA5 script.

    Cuts are applied before every requested histogram. Version 1 does
    not support separate pre-cut and post-cut histogram regions.
    """

    event_file = _safe_path(
        input_file,
        label="MadAnalysis input file",
    )

    job_dir = _safe_path(
        job_directory,
        label="MadAnalysis job directory",
    )

    available_particles = (
        _available_analysis_particles(
            workflow
        )
    )

    cuts = tuple(
        _compile_analysis_cut(
            cut,
            available_particles=(
                available_particles
            ),
        )
        for cut in plan.cuts
    )

    plots = tuple(
        _compile_analysis_histogram(
            histogram,
            available_particles=(
                available_particles
            ),
        )
        for histogram in plan.histograms
    )

    commands = (
        f"import {event_file} as sample",
        *cuts,
        *plots,
        f"submit {job_dir}",
        "quit",
    )

    artifact = MadAnalysisArtifact(
        level=level,
        input_file=event_file,
        job_directory=job_dir,
        commands=commands,
        expected_plot_count=len(plots),
        expected_cut_count=len(cuts),
    )

    report = validate_madanalysis_artifact(
        artifact
    )

    if not report.is_valid:
        messages = "; ".join(
            issue.message
            for issue in report.issues
        )

        raise MadAnalysisBuildError(
            messages
        )

    return artifact
