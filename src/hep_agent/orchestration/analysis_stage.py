"""Orchestration for separate MadAnalysis post-processing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from hep_agent.analysis import (
    MadAnalysisArtifact,
    MadAnalysisBuildError,
    MadAnalysisExecutionResult,
    MadAnalysisLevel,
    build_madanalysis_quicklook,
    run_madanalysis_artifact,
)
from hep_agent.analysis.madanalysis import (
    build_madanalysis_from_plan,
)
from hep_agent.execution import MadGraphPhysicsResult
from hep_agent.schemas import WorkflowIntent


class AnalysisStageFailureCategory(str, Enum):
    """Failures before or during the MA5 post-processing stage."""

    INPUT_SELECTION = "analysis_input_selection_failure"
    BUILD = "analysis_build_failure"
    CONFIGURATION = "analysis_configuration_failure"
    EXECUTION = "analysis_execution_failure"


@dataclass(frozen=True)
class AnalysisInputSelection:
    """The event file and MA5 mode selected for post-processing."""

    input_file: Path
    level: MadAnalysisLevel


@dataclass(frozen=True)
class AnalysisStageResult:
    """Result of the complete deterministic MA5 stage."""

    requested: bool
    success: bool

    selection: AnalysisInputSelection | None = None
    artifact: MadAnalysisArtifact | None = None
    execution: MadAnalysisExecutionResult | None = None

    failure_category: AnalysisStageFailureCategory | None = None
    failure_message: str | None = None


def select_madanalysis_input(
    physics: MadGraphPhysicsResult,
) -> AnalysisInputSelection | None:
    """Choose the highest available MA5 input level.

    A managed Delphes ROOT file is preferred so the analysis stage validates
    the same detector output and ROOT/Delphes linkage as the simulation.
    """

    if (
        physics.detector_root_file is not None
        and physics.detector_root_file.is_file()
    ):
        return AnalysisInputSelection(
            input_file=physics.detector_root_file,
            level=MadAnalysisLevel.RECONSTRUCTED,
        )

    if (
        physics.showered_hepmc_file is not None
        and physics.showered_hepmc_file.is_file()
    ):
        return AnalysisInputSelection(
            input_file=physics.showered_hepmc_file,
            level=MadAnalysisLevel.HADRON,
        )

    if (
        physics.primary_lhe_file is not None
        and physics.primary_lhe_file.is_file()
    ):
        return AnalysisInputSelection(
            input_file=physics.primary_lhe_file,
            level=MadAnalysisLevel.PARTON,
        )

    return None


def run_madanalysis_stage(
    workflow: WorkflowIntent,
    physics: MadGraphPhysicsResult,
    *,
    madanalysis_executable: str | Path | None,
    analysis_directory: str | Path,
    timeout_seconds: float = 300,
    stack_manifest: str | Path | None = None,
    unsupported_nonhermetic: bool = False,
) -> AnalysisStageResult:
    """Build and execute a separate deterministic MA5 quick-look."""

    if not workflow.pipeline.madanalysis:
        return AnalysisStageResult(
            requested=False,
            success=True,
        )

    selection = select_madanalysis_input(physics)

    if selection is None:
        return AnalysisStageResult(
            requested=True,
            success=False,
            failure_category=(
                AnalysisStageFailureCategory.INPUT_SELECTION
            ),
            failure_message=(
                "MadAnalysis was requested, but no supported "
                "HepMC or LHE event file was found."
            ),
        )

    if madanalysis_executable is None:
        return AnalysisStageResult(
            requested=True,
            success=False,
            selection=selection,
            failure_category=(
                AnalysisStageFailureCategory.CONFIGURATION
            ),
            failure_message=(
                "MadAnalysis was requested, but no MA5 executable "
                "was configured."
            ),
        )

    analysis_dir = (
        Path(analysis_directory)
        .expanduser()
        .resolve()
    )

    if workflow.analysis is None:
        job_directory = (
            analysis_dir
            / "quicklook_job"
        )
    else:
        job_directory = (
            analysis_dir
            / "structured_job"
        )

    try:
        if workflow.analysis is None:
            artifact = (
                build_madanalysis_quicklook(
                    workflow,
                    input_file=(
                        selection.input_file
                    ),
                    job_directory=(
                        job_directory
                    ),
                    level=selection.level,
                )
            )
        else:
            artifact = (
                build_madanalysis_from_plan(
                    workflow,
                    workflow.analysis,
                    input_file=(
                        selection.input_file
                    ),
                    job_directory=(
                        job_directory
                    ),
                    level=selection.level,
                )
            )

    except MadAnalysisBuildError as exc:
        return AnalysisStageResult(
            requested=True,
            success=False,
            selection=selection,
            failure_category=(
                AnalysisStageFailureCategory.BUILD
            ),
            failure_message=str(exc),
        )

    execution = run_madanalysis_artifact(
        artifact,
        madanalysis_executable=madanalysis_executable,
        analysis_directory=analysis_dir,
        timeout_seconds=timeout_seconds,
        stack_manifest=stack_manifest,
        unsupported_nonhermetic=unsupported_nonhermetic,
    )

    if not execution.success:
        detail = execution.failure_message

        if execution.failure_category is not None:
            detail = (
                f"{execution.failure_category.value}: "
                f"{detail}"
            )

        return AnalysisStageResult(
            requested=True,
            success=False,
            selection=selection,
            artifact=artifact,
            execution=execution,
            failure_category=(
                AnalysisStageFailureCategory.EXECUTION
            ),
            failure_message=detail,
        )

    return AnalysisStageResult(
        requested=True,
        success=True,
        selection=selection,
        artifact=artifact,
        execution=execution,
    )
