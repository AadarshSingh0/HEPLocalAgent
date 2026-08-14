"""Complete local-agent preparation and external execution."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from hep_agent.execution import (
    MadGraphExecutionResult,
    MadGraphPhysicsResult,
    parse_madgraph_result,
    run_madgraph_workflow,
)
from hep_agent.execution.outcome import (
    validate_execution_outputs,
)
from hep_agent.models import AgentProfile, OllamaClient
from hep_agent.orchestration.analysis_stage import (
    AnalysisStageFailureCategory,
    AnalysisStageResult,
    run_madanalysis_stage,
)
from hep_agent.orchestration.approval import ApprovalResult
from hep_agent.orchestration.preexecution import (
    PreExecutionResult,
    PreExecutionStatus,
    ProgressObserver,
)
from hep_agent.orchestration.run_record import (
    PreExecutionRunRecord,
    RecordedPreExecution,
    mark_record_cancelled,
    run_preexecution_and_record,
    save_run_record,
    update_record_after_execution,
)


class EndToEndStatus(str, Enum):
    """Final status of one complete agent request."""

    COMPLETED = "completed"
    EXECUTION_FAILED = "execution_failed"
    ANALYSIS_FAILED = "analysis_failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    PREEXECUTION_FAILED = "preexecution_failed"


ApprovalResolver = Callable[[ApprovalResult], bool]
PreExecutionObserver = Callable[[PreExecutionResult], None]


@dataclass(frozen=True)
class PreparedEndToEnd:
    """A validated workflow prepared for later execution.

    The prepared object contains the exact deterministic artifact shown
    to the user for approval. Executing it does not call the planner
    again.
    """

    preexecution: RecordedPreExecution
    preexecution_wall_time_seconds: float

    @property
    def result(self) -> PreExecutionResult:
        """Return the underlying pre-execution result."""

        return self.preexecution.result

    @property
    def record(self) -> PreExecutionRunRecord:
        """Return the current persistent run record."""

        return self.preexecution.record

    @property
    def is_ready(self) -> bool:
        """Whether this workflow can be offered for execution."""

        return self.result.is_ready


@dataclass(frozen=True)
class EndToEndResult:
    """Final result of one complete local-agent request."""

    status: EndToEndStatus
    preexecution: RecordedPreExecution
    final_record: PreExecutionRunRecord

    execution: MadGraphExecutionResult | None = None
    physics: MadGraphPhysicsResult | None = None
    analysis: AnalysisStageResult | None = None

    @property
    def success(self) -> bool:
        return self.status == EndToEndStatus.COMPLETED


def prepare_end_to_end(
    user_request: str,
    *,
    client: OllamaClient,
    profile_name: str,
    profile: AgentProfile,
    records_directory: str | Path = "results/runs",
    progress_observer: ProgressObserver | None = None,
) -> PreparedEndToEnd:
    """Plan and validate a request without executing HEP software."""

    start = time.perf_counter()

    recorded = run_preexecution_and_record(
        user_request,
        client=client,
        profile_name=profile_name,
        profile=profile,
        output_directory=records_directory,
        progress_observer=progress_observer,
    )

    elapsed = time.perf_counter() - start

    return PreparedEndToEnd(
        preexecution=recorded,
        preexecution_wall_time_seconds=elapsed,
    )


def _unready_status(
    result: PreExecutionResult,
) -> EndToEndStatus:
    """Map an unready pre-execution result to final status."""

    if result.status == PreExecutionStatus.FAILED:
        return EndToEndStatus.PREEXECUTION_FAILED

    return EndToEndStatus.BLOCKED


def execute_prepared(
    prepared: PreparedEndToEnd,
    *,
    approved: bool,
    mg5_executable: str | Path,
    madanalysis_executable: str | Path | None = None,
    records_directory: str | Path = "results/runs",
    executions_directory: str | Path = "results/executions",
    analyses_directory: str | Path = "results/analyses",
    project_root: str | Path = ".",
    analysis_timeout_seconds: float = 300,
    stack_manifest: str | Path | None = None,
    unsupported_nonhermetic: bool = False,
) -> EndToEndResult:
    """Execute an already prepared deterministic workflow.

    This function never calls the planner or repair models.
    """

    recorded = prepared.preexecution
    preexecution_result = recorded.result

    if not preexecution_result.is_ready:
        return EndToEndResult(
            status=_unready_status(
                preexecution_result
            ),
            preexecution=recorded,
            final_record=recorded.record,
        )

    if (
        preexecution_result.approval is None
        or preexecution_result.artifact is None
        or preexecution_result.workflow is None
    ):
        raise RuntimeError(
            "A ready pre-execution result is missing workflow, "
            "approval, or artifact information."
        )

    if not approved:
        final_record = mark_record_cancelled(
            recorded.record,
            end_to_end_wall_time_seconds=(
                prepared.preexecution_wall_time_seconds
            ),
        )

        save_run_record(
            final_record,
            records_directory,
        )

        return EndToEndResult(
            status=EndToEndStatus.CANCELLED,
            preexecution=recorded,
            final_record=final_record,
        )

    active_execution_start = time.perf_counter()
    workflow = preexecution_result.workflow

    execution_directory = (
        Path(executions_directory)
        / recorded.record.run_id
    )

    execution = run_madgraph_workflow(
        preexecution_result.artifact,
        mg5_executable=mg5_executable,
        run_directory=execution_directory,
        timeout_seconds=workflow.run.timeout_seconds,
        stack_manifest=stack_manifest,
        unsupported_nonhermetic=unsupported_nonhermetic,
    )

    physics: MadGraphPhysicsResult | None = None

    if (
        execution.stdout_path is not None
        and execution.stdout_path.is_file()
    ):
        stdout_text = execution.stdout_path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        physics = parse_madgraph_result(
            stdout_text=stdout_text,
            execution_directory=execution_directory,
        )

    output_validation = validate_execution_outputs(
        execution,
        physics,
        require_lhe=True,
        require_hepmc=workflow.pipeline.pythia8,
        require_root=workflow.pipeline.delphes,
    )
    validated_execution_success = output_validation.is_valid

    analysis: AnalysisStageResult | None = None

    if validated_execution_success:
        if physics is not None:
            analysis = run_madanalysis_stage(
                workflow,
                physics,
                madanalysis_executable=(
                    madanalysis_executable
                ),
                analysis_directory=(
                    Path(analyses_directory)
                    / recorded.record.run_id
                ),
                timeout_seconds=(
                    analysis_timeout_seconds
                ),
                stack_manifest=stack_manifest,
                unsupported_nonhermetic=unsupported_nonhermetic,
            )

        elif workflow.pipeline.madanalysis:
            analysis = AnalysisStageResult(
                requested=True,
                success=False,
                failure_category=(
                    AnalysisStageFailureCategory
                    .INPUT_SELECTION
                ),
                failure_message=(
                    "MadAnalysis was requested, but the "
                    "MadGraph result parser did not return "
                    "an event-file summary."
                ),
            )

    execution_elapsed = (
        time.perf_counter()
        - active_execution_start
    )

    active_total = (
        prepared.preexecution_wall_time_seconds
        + execution_elapsed
    )

    final_record = update_record_after_execution(
        recorded.record,
        execution=execution,
        physics=physics,
        analysis=analysis,
        output_validation=output_validation,
        analysis_was_requested=(
            workflow.pipeline.madanalysis
        ),
        execution_directory=execution_directory,
        project_root=project_root,
        end_to_end_wall_time_seconds=active_total,
    )

    save_run_record(
        final_record,
        records_directory,
    )

    if not validated_execution_success:
        status = EndToEndStatus.EXECUTION_FAILED

    elif (
        analysis is not None
        and analysis.requested
        and not analysis.success
    ):
        status = EndToEndStatus.ANALYSIS_FAILED

    else:
        status = EndToEndStatus.COMPLETED

    return EndToEndResult(
        status=status,
        preexecution=recorded,
        final_record=final_record,
        execution=execution,
        physics=physics,
        analysis=analysis,
    )


def run_end_to_end(
    user_request: str,
    *,
    client: OllamaClient,
    profile_name: str,
    profile: AgentProfile,
    mg5_executable: str | Path,
    approval_resolver: ApprovalResolver,
    madanalysis_executable: str | Path | None = None,
    preexecution_observer: PreExecutionObserver | None = None,
    records_directory: str | Path = "results/runs",
    executions_directory: str | Path = "results/executions",
    analyses_directory: str | Path = "results/analyses",
    project_root: str | Path = ".",
    analysis_timeout_seconds: float = 300,
    stack_manifest: str | Path | None = None,
    unsupported_nonhermetic: bool = False,
) -> EndToEndResult:
    """Run the existing one-command CLI-compatible workflow."""

    prepared = prepare_end_to_end(
        user_request,
        client=client,
        profile_name=profile_name,
        profile=profile,
        records_directory=records_directory,
    )

    preexecution_result = prepared.result

    if preexecution_observer is not None:
        preexecution_observer(
            preexecution_result
        )

    approved = False

    if preexecution_result.is_ready:
        if preexecution_result.approval is None:
            raise RuntimeError(
                "A ready pre-execution result is missing "
                "its approval decision."
            )

        approved = approval_resolver(
            preexecution_result.approval
        )

    return execute_prepared(
        prepared,
        approved=approved,
        mg5_executable=mg5_executable,
        madanalysis_executable=(
            madanalysis_executable
        ),
        records_directory=records_directory,
        executions_directory=executions_directory,
        analyses_directory=analyses_directory,
        project_root=project_root,
        analysis_timeout_seconds=(
            analysis_timeout_seconds
        ),
        stack_manifest=stack_manifest,
        unsupported_nonhermetic=unsupported_nonhermetic,
    )
