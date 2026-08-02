"""Tests for energy-scan preparation through the existing planner."""

import unittest
from unittest.mock import patch

from hep_agent.orchestration.preexecution import (
    PreExecutionResult,
    PreExecutionStatus,
)
from hep_agent.scans import (
    prepare_energy_scan,
)

from test_energy_scan import make_workflow


SCAN_REQUEST = (
    "Simulate proton-proton collisions producing an electron "
    "and a positron. Do an energy scan from 1 TeV to 5 TeV "
    "in steps of 500 GeV. Generate 100 events per point."
)


class EnergyScanPreparationTests(unittest.TestCase):
    @patch(
        "hep_agent.scans.preparation."
        "run_preexecution_loop"
    )
    def test_ordinary_request_returns_none(
        self,
        run_preexecution,
    ) -> None:
        prepared = prepare_energy_scan(
            "Simulate p p collisions at 13 TeV.",
            client=object(),
            profile=object(),
        )

        self.assertIsNone(prepared)
        run_preexecution.assert_not_called()

    @patch(
        "hep_agent.scans.preparation."
        "run_preexecution_loop"
    )
    def test_scan_uses_cleaned_base_request(
        self,
        run_preexecution,
    ) -> None:
        workflow = make_workflow()

        run_preexecution.return_value = (
            PreExecutionResult(
                status=(
                    PreExecutionStatus
                    .READY_FOR_APPROVAL
                ),
                user_request="base",
                workflow=workflow,
            )
        )

        prepared = prepare_energy_scan(
            SCAN_REQUEST,
            client=object(),
            profile=object(),
        )

        self.assertIsNotNone(prepared)

        called_request = (
            run_preexecution.call_args.args[0]
        )

        self.assertIn(
            "at a total centre-of-mass energy of 1 TEV",
            called_request,
        )
        self.assertNotIn(
            "500 GeV",
            called_request,
        )
        self.assertNotIn(
            "5 TeV",
            called_request,
        )

    @patch(
        "hep_agent.scans.preparation."
        "run_preexecution_loop"
    )
    def test_scan_expands_to_nine_points(
        self,
        run_preexecution,
    ) -> None:
        run_preexecution.return_value = (
            PreExecutionResult(
                status=(
                    PreExecutionStatus
                    .READY_FOR_APPROVAL
                ),
                user_request="base",
                workflow=make_workflow(
                    nevents=100
                ),
            )
        )

        prepared = prepare_energy_scan(
            SCAN_REQUEST,
            client=object(),
            profile=object(),
        )

        self.assertIsNotNone(prepared)

        assert prepared is not None

        self.assertTrue(prepared.is_ready)
        self.assertEqual(
            prepared.point_count,
            9,
        )
        self.assertEqual(
            prepared.total_requested_events,
            900,
        )

        assert prepared.expanded is not None

        self.assertEqual(
            [
                point.energy_gev
                for point in prepared.expanded.points
            ],
            [
                1000.0,
                1500.0,
                2000.0,
                2500.0,
                3000.0,
                3500.0,
                4000.0,
                4500.0,
                5000.0,
            ],
        )

    @patch(
        "hep_agent.scans.preparation."
        "run_preexecution_loop"
    )
    def test_planner_failure_produces_unready_scan(
        self,
        run_preexecution,
    ) -> None:
        run_preexecution.return_value = (
            PreExecutionResult(
                status=PreExecutionStatus.FAILED,
                user_request="base",
                failure_message=(
                    "Synthetic planner failure."
                ),
            )
        )

        prepared = prepare_energy_scan(
            SCAN_REQUEST,
            client=object(),
            profile=object(),
        )

        self.assertIsNotNone(prepared)

        assert prepared is not None

        self.assertFalse(prepared.is_ready)
        self.assertEqual(
            prepared.point_count,
            0,
        )
        self.assertEqual(
            prepared.failure_message,
            "Synthetic planner failure.",
        )

    @patch(
        "hep_agent.scans.preparation."
        "run_preexecution_loop"
    )
    def test_pipeline_is_preserved_at_every_point(
        self,
        run_preexecution,
    ) -> None:
        workflow = make_workflow(
            nevents=250
        )

        workflow = workflow.model_copy(
            update={
                "pipeline": (
                    workflow.pipeline.model_copy(
                        update={
                            "pythia8": True,
                            "madanalysis": True,
                        }
                    )
                )
            },
            deep=True,
        )

        run_preexecution.return_value = (
            PreExecutionResult(
                status=(
                    PreExecutionStatus
                    .READY_FOR_APPROVAL
                ),
                user_request="base",
                workflow=workflow,
            )
        )

        prepared = prepare_energy_scan(
            SCAN_REQUEST,
            client=object(),
            profile=object(),
        )

        assert prepared is not None
        assert prepared.expanded is not None

        for point in prepared.expanded.points:
            self.assertEqual(
                point.workflow.run.nevents,
                250,
            )
            self.assertTrue(
                point.workflow.pipeline.pythia8
            )
            self.assertTrue(
                point.workflow.pipeline.madanalysis
            )


if __name__ == "__main__":
    unittest.main()
