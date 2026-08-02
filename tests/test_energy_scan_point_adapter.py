"""Tests for the existing-pipeline scan-point adapter."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hep_agent.builders.madgraph_workflow import (
    build_madgraph_workflow_artifact,
)
from hep_agent.models import (
    load_agent_profiles,
)
from hep_agent.orchestration.approval import (
    ApprovalContext,
    decide_approval,
)
from hep_agent.orchestration.preexecution import (
    PreExecutionResult,
    PreExecutionStatus,
)
from hep_agent.scans import (
    ExistingPipelinePointExecutor,
    build_energy_scan_plan,
    expand_energy_scan,
)
from hep_agent.validation.madgraph_workflow import (
    validate_madgraph_workflow_artifact,
)

from test_energy_scan import make_workflow


def make_prepared_scan():
    workflow = make_workflow(
        nevents=100,
        seed=0,
    )

    artifact = (
        build_madgraph_workflow_artifact(
            workflow
        )
    )

    report = (
        validate_madgraph_workflow_artifact(
            workflow,
            artifact,
        )
    )

    approval = decide_approval(
        workflow,
        report,
        context=ApprovalContext(
            repair_changed_physics=False
        ),
    )

    base_result = PreExecutionResult(
        status=(
            PreExecutionStatus
            .READY_FOR_APPROVAL
        ),
        user_request="Synthetic scan base.",
        workflow=workflow,
        artifact=artifact,
        approval=approval,
        artifact_report=report,
    )

    plan = build_energy_scan_plan(
        workflow,
        energy_points_gev=[
            1000,
            1500,
            2000,
        ],
    )

    expanded = expand_energy_scan(plan)

    prepared_scan = SimpleNamespace(
        is_ready=True,
        original_request=(
            "Scan from 1 to 2 TeV."
        ),
        point_count=expanded.point_count,
        base_result=base_result,
    )

    return prepared_scan, expanded


class EnergyScanPointAdapterTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        profiles = load_agent_profiles(
            Path(
                "configs/agent_profiles.json"
            )
        )

        self.profile = profiles[
            "qwen_primary"
        ]

    @patch(
        "hep_agent.scans.point_adapter."
        "execute_prepared"
    )
    def test_point_uses_existing_pipeline(
        self,
        execute_prepared_mock,
    ) -> None:
        prepared_scan, expanded = (
            make_prepared_scan()
        )

        point = expanded.points[0]

        final_record = SimpleNamespace(
            execution_success=True,
            execution_failure_category=None,
            analysis_requested=False,
            analysis_success=None,
            analysis_failure_message=None,
            analysis_failure_category=None,
            cross_section_pb=12.5,
            cross_section_uncertainty_pb=0.3,
            generated_event_count=100,
        )

        execute_prepared_mock.return_value = (
            SimpleNamespace(
                success=True,
                status=SimpleNamespace(
                    value="completed"
                ),
                final_record=final_record,
            )
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            executor = (
                ExistingPipelinePointExecutor(
                    prepared_scan=prepared_scan,
                    scan_id="test_scan",
                    profile_name="qwen_primary",
                    profile=self.profile,
                    mg5_executable="/synthetic/mg5",
                    records_directory=(
                        root / "runs"
                    ),
                    executions_directory=(
                        root / "executions"
                    ),
                    analyses_directory=(
                        root / "analyses"
                    ),
                    project_root=root,
                )
            )

            outcome = executor(point)

            self.assertTrue(outcome.success)
            self.assertEqual(
                outcome.cross_section_pb,
                12.5,
            )

            record_path = Path(
                outcome.point_record_path
            )

            self.assertTrue(
                record_path.is_file()
            )

        execute_prepared_mock.assert_called_once()

        passed_prepared = (
            execute_prepared_mock
            .call_args
            .args[0]
        )

        self.assertEqual(
            passed_prepared
            .result
            .llm_call_count,
            0,
        )

        commands = (
            passed_prepared
            .result
            .artifact
            .commands
        )

        self.assertIn(
            "set ebeam1 500",
            commands,
        )
        self.assertIn(
            "set ebeam2 500",
            commands,
        )
        self.assertIn(
            "set iseed 1001",
            commands,
        )

    @patch(
        "hep_agent.scans.point_adapter."
        "execute_prepared"
    )
    def test_pipeline_failure_is_returned(
        self,
        execute_prepared_mock,
    ) -> None:
        prepared_scan, expanded = (
            make_prepared_scan()
        )

        final_record = SimpleNamespace(
            execution_success=False,
            execution_failure_category=(
                "nonzero_exit"
            ),
            analysis_requested=False,
            analysis_success=None,
            analysis_failure_message=None,
            analysis_failure_category=None,
            cross_section_pb=None,
            cross_section_uncertainty_pb=None,
            generated_event_count=None,
        )

        execute_prepared_mock.return_value = (
            SimpleNamespace(
                success=False,
                status=SimpleNamespace(
                    value="execution_failed"
                ),
                final_record=final_record,
            )
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            executor = (
                ExistingPipelinePointExecutor(
                    prepared_scan=prepared_scan,
                    scan_id="test_failure",
                    profile_name="qwen_primary",
                    profile=self.profile,
                    mg5_executable="/synthetic/mg5",
                    records_directory=(
                        root / "runs"
                    ),
                    executions_directory=(
                        root / "executions"
                    ),
                    analyses_directory=(
                        root / "analyses"
                    ),
                    project_root=root,
                )
            )

            outcome = executor(
                expanded.points[0]
            )

        self.assertFalse(outcome.success)
        self.assertIn(
            "MadGraph execution failed",
            outcome.failure_message or "",
        )
        self.assertIsNotNone(
            outcome.point_record_path
        )

    def test_unsafe_scan_id_is_rejected(
        self,
    ) -> None:
        prepared_scan, _ = (
            make_prepared_scan()
        )

        with self.assertRaises(
            ValueError
        ):
            ExistingPipelinePointExecutor(
                prepared_scan=prepared_scan,
                scan_id="../unsafe",
                profile_name="qwen_primary",
                profile=self.profile,
                mg5_executable="/synthetic/mg5",
            )

    def test_unready_scan_is_rejected(
        self,
    ) -> None:
        prepared_scan, _ = (
            make_prepared_scan()
        )

        prepared_scan.is_ready = False

        with self.assertRaises(
            ValueError
        ):
            ExistingPipelinePointExecutor(
                prepared_scan=prepared_scan,
                scan_id="unready",
                profile_name="qwen_primary",
                profile=self.profile,
                mg5_executable="/synthetic/mg5",
            )


if __name__ == "__main__":
    unittest.main()
