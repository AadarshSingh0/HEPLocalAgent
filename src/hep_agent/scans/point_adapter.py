"""Adapter from deterministic scan points to the existing HEP pipeline.

Each point:

1. receives an already validated WorkflowIntent;
2. builds its MG5 artifact deterministically;
3. validates that artifact;
4. creates an ordinary point-level run record;
5. invokes the existing execute_prepared() controller;
6. returns a runner-neutral PointExecutionOutcome.

No planner or repair model is called for individual scan points.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from hep_agent.builders.madgraph_workflow import (
    build_madgraph_workflow_artifact,
)
from hep_agent.models import AgentProfile
from hep_agent.orchestration.end_to_end import (
    PreparedEndToEnd,
    execute_prepared,
)
from hep_agent.orchestration.preexecution import (
    PreExecutionResult,
    PreExecutionStatus,
)
from hep_agent.orchestration.run_record import (
    RecordedPreExecution,
    build_preexecution_run_record,
    save_run_record,
)
from hep_agent.scans.energy_scan import (
    EnergyScanPoint,
)
from hep_agent.scans.execution import (
    PointExecutionOutcome,
)
from hep_agent.scans.preparation import (
    PreparedEnergyScan,
)
from hep_agent.validation.madgraph_workflow import (
    validate_madgraph_workflow_artifact,
)


_SAFE_SCAN_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
)


@dataclass(frozen=True)
class ExistingPipelinePointExecutor:
    """Execute scan points through the existing single-run stack."""

    prepared_scan: PreparedEnergyScan

    scan_id: str

    profile_name: str
    profile: AgentProfile

    mg5_executable: str | Path
    madanalysis_executable: str | Path | None = None

    records_directory: str | Path = "results/runs"
    executions_directory: str | Path = "results/executions"
    analyses_directory: str | Path = "results/analyses"

    project_root: str | Path = "."
    analysis_timeout_seconds: float = 300

    def __post_init__(self) -> None:
        """Reject incomplete or unsafe adapter construction."""

        if not self.prepared_scan.is_ready:
            raise ValueError(
                "The energy scan must be ready before "
                "constructing its point executor."
            )

        if (
            self.prepared_scan
            .base_result
            .approval
            is None
        ):
            raise ValueError(
                "The prepared scan base workflow is "
                "missing its approval information."
            )

        if not _SAFE_SCAN_ID.fullmatch(
            self.scan_id
        ):
            raise ValueError(
                "scan_id may contain only letters, "
                "numbers, underscores, and hyphens."
            )

    def _point_run_id(
        self,
        point: EnergyScanPoint,
    ) -> str:
        """Return a deterministic point-level run identifier."""

        return (
            f"{self.scan_id}"
            f"_point_{point.index + 1:03d}"
        )

    def _point_request(
        self,
        point: EnergyScanPoint,
    ) -> str:
        """Describe how this point was derived from the scan."""

        return (
            f"{self.prepared_scan.original_request}\n\n"
            "[Deterministic scan expansion]\n"
            f"Point: {point.index + 1} of "
            f"{self.prepared_scan.point_count}\n"
            f"Centre-of-mass energy: "
            f"{point.energy_gev:g} GeV\n"
            f"Random seed: {point.random_seed}\n"
            f"Output name: {point.output_name}"
        )

    @staticmethod
    def _artifact_failure_message(
        artifact_report,
    ) -> str:
        """Format deterministic artifact-validation errors."""

        errors = getattr(
            artifact_report,
            "errors",
            (),
        )

        messages = [
            getattr(
                issue,
                "message",
                str(issue),
            )
            for issue in errors
        ]

        if not messages:
            return (
                "The deterministic scan-point artifact "
                "failed validation."
            )

        return (
            "The deterministic scan-point artifact "
            "failed validation: "
            + " | ".join(messages)
        )

    @staticmethod
    def _execution_failure_message(
        final_record,
        status_value: str,
    ) -> str:
        """Describe a failed existing-pipeline execution."""

        if final_record.execution_success is False:
            category = (
                final_record
                .execution_failure_category
                or "unknown"
            )

            return (
                "MadGraph execution failed "
                f"({category})."
            )

        if (
            final_record.analysis_requested
            and final_record.analysis_success
            is False
        ):
            detail = (
                final_record
                .analysis_failure_message
                or final_record
                .analysis_failure_category
                or "unknown analysis failure"
            )

            return (
                "MadAnalysis failed: "
                f"{detail}"
            )

        return (
            "The point pipeline finished with "
            f"status {status_value}."
        )

    def __call__(
        self,
        point: EnergyScanPoint,
    ) -> PointExecutionOutcome:
        """Execute one point without any additional LLM call."""

        preparation_started = (
            time.perf_counter()
        )

        artifact = (
            build_madgraph_workflow_artifact(
                point.workflow
            )
        )

        artifact_report = (
            validate_madgraph_workflow_artifact(
                point.workflow,
                artifact,
            )
        )

        if not artifact_report.is_valid:
            return PointExecutionOutcome(
                success=False,
                failure_message=(
                    self._artifact_failure_message(
                        artifact_report
                    )
                ),
            )

        point_preexecution = PreExecutionResult(
            status=(
                PreExecutionStatus
                .READY_FOR_APPROVAL
            ),
            user_request=(
                self._point_request(point)
            ),
            workflow=point.workflow,
            artifact=artifact,
            approval=(
                self.prepared_scan
                .base_result
                .approval
            ),
            artifact_report=artifact_report,

            # The LLM was called once at scan preparation,
            # not once per point.
            model_calls=(),
            corrections=(),
            repair_attempts=0,
            fallback_used=False,
        )

        preparation_elapsed = (
            time.perf_counter()
            - preparation_started
        )

        run_id = self._point_run_id(
            point
        )

        record = (
            build_preexecution_run_record(
                result=point_preexecution,
                profile_name=(
                    self.profile_name
                ),
                profile=self.profile,
                total_wall_time_seconds=(
                    preparation_elapsed
                ),
                run_id=run_id,
            )
        )

        record_path = save_run_record(
            record,
            self.records_directory,
        )

        recorded = RecordedPreExecution(
            result=point_preexecution,
            record=record,
            record_path=record_path,
        )

        prepared = PreparedEndToEnd(
            preexecution=recorded,
            preexecution_wall_time_seconds=(
                preparation_elapsed
            ),
        )

        final_result = execute_prepared(
            prepared,
            approved=True,
            mg5_executable=(
                self.mg5_executable
            ),
            madanalysis_executable=(
                self.madanalysis_executable
            ),
            records_directory=(
                self.records_directory
            ),
            executions_directory=(
                self.executions_directory
            ),
            analyses_directory=(
                self.analyses_directory
            ),
            project_root=self.project_root,
            analysis_timeout_seconds=(
                self.analysis_timeout_seconds
            ),
        )

        final_record = (
            final_result.final_record
        )

        if not final_result.success:
            return PointExecutionOutcome(
                success=False,
                failure_message=(
                    self._execution_failure_message(
                        final_record,
                        final_result.status.value,
                    )
                ),
                point_record_path=record_path,
            )

        if (
            final_record.cross_section_pb
            is None
        ):
            return PointExecutionOutcome(
                success=False,
                failure_message=(
                    "The point pipeline completed, but "
                    "no cross section was parsed."
                ),
                point_record_path=record_path,
            )

        return PointExecutionOutcome(
            success=True,
            cross_section_pb=(
                final_record.cross_section_pb
            ),
            cross_section_uncertainty_pb=(
                final_record
                .cross_section_uncertainty_pb
            ),
            generated_event_count=(
                final_record
                .generated_event_count
            ),
            point_record_path=record_path,
        )
