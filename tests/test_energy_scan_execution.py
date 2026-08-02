"""Tests for sequential scan execution and aggregation."""

import json
import tempfile
import unittest
from pathlib import Path

from hep_agent.scans import (
    EnergyScanStatus,
    PointExecutionOutcome,
    ScanPointStatus,
    build_energy_scan_plan,
    execute_energy_scan,
    expand_energy_scan,
)

from test_energy_scan import make_workflow


def make_expanded_scan(
    *,
    continue_on_failure: bool = True,
):
    plan = build_energy_scan_plan(
        make_workflow(
            nevents=100
        ),
        energy_points_gev=[
            1000,
            1500,
            2000,
        ],
        continue_on_failure=(
            continue_on_failure
        ),
    )

    return expand_energy_scan(plan)


class EnergyScanExecutionTests(
    unittest.TestCase
):
    def test_complete_scan_finds_interior_maximum(
        self,
    ) -> None:
        expanded = make_expanded_scan()

        values = {
            1000.0: (10.0, 0.5),
            1500.0: (20.0, 0.6),
            2000.0: (15.0, 0.5),
        }

        def executor(point):
            value, uncertainty = values[
                point.energy_gev
            ]

            return PointExecutionOutcome(
                success=True,
                cross_section_pb=value,
                cross_section_uncertainty_pb=(
                    uncertainty
                ),
                generated_event_count=100,
            )

        with tempfile.TemporaryDirectory() as temporary:
            summary = execute_energy_scan(
                expanded,
                point_executor=executor,
                output_directory=temporary,
                scan_id="test_complete",
            )

            self.assertEqual(
                summary.status,
                EnergyScanStatus.COMPLETED,
            )
            self.assertEqual(
                summary.completed_point_count,
                3,
            )

            self.assertIsNotNone(
                summary.maximum
            )

            assert summary.maximum is not None

            self.assertEqual(
                summary.maximum.energy_gev,
                1500.0,
            )
            self.assertFalse(
                summary.maximum.at_scan_boundary
            )

    def test_boundary_maximum_produces_warning(
        self,
    ) -> None:
        expanded = make_expanded_scan()

        def executor(point):
            return PointExecutionOutcome(
                success=True,
                cross_section_pb=(
                    point.energy_gev
                    / 100.0
                ),
                cross_section_uncertainty_pb=0.1,
                generated_event_count=100,
            )

        with tempfile.TemporaryDirectory() as temporary:
            summary = execute_energy_scan(
                expanded,
                point_executor=executor,
                output_directory=temporary,
                scan_id="test_boundary",
            )

        assert summary.maximum is not None

        self.assertTrue(
            summary.maximum.at_scan_boundary
        )
        self.assertTrue(
            summary.maximum.warnings
        )

    def test_continue_after_one_failure(
        self,
    ) -> None:
        expanded = make_expanded_scan(
            continue_on_failure=True
        )

        calls = []

        def executor(point):
            calls.append(point.index)

            if point.index == 1:
                return PointExecutionOutcome(
                    success=False,
                    failure_message=(
                        "Synthetic failure."
                    ),
                )

            return PointExecutionOutcome(
                success=True,
                cross_section_pb=1.0,
                generated_event_count=100,
            )

        with tempfile.TemporaryDirectory() as temporary:
            summary = execute_energy_scan(
                expanded,
                point_executor=executor,
                output_directory=temporary,
                scan_id="test_continue",
            )

        self.assertEqual(
            calls,
            [0, 1, 2],
        )
        self.assertEqual(
            summary.status,
            EnergyScanStatus.PARTIAL,
        )
        self.assertEqual(
            summary.completed_point_count,
            2,
        )
        self.assertEqual(
            summary.failed_point_count,
            1,
        )

    def test_stop_policy_skips_remaining_points(
        self,
    ) -> None:
        expanded = make_expanded_scan(
            continue_on_failure=False
        )

        calls = []

        def executor(point):
            calls.append(point.index)

            if point.index == 1:
                return PointExecutionOutcome(
                    success=False,
                    failure_message=(
                        "Synthetic failure."
                    ),
                )

            return PointExecutionOutcome(
                success=True,
                cross_section_pb=1.0,
                generated_event_count=100,
            )

        with tempfile.TemporaryDirectory() as temporary:
            summary = execute_energy_scan(
                expanded,
                point_executor=executor,
                output_directory=temporary,
                scan_id="test_stop",
            )

        self.assertEqual(
            calls,
            [0, 1],
        )
        self.assertEqual(
            summary.skipped_point_count,
            1,
        )
        self.assertEqual(
            summary.point_results[2].status,
            ScanPointStatus.SKIPPED,
        )

    def test_executor_exception_is_recorded(
        self,
    ) -> None:
        expanded = make_expanded_scan()

        def executor(point):
            if point.index == 0:
                raise RuntimeError(
                    "Synthetic exception."
                )

            return PointExecutionOutcome(
                success=True,
                cross_section_pb=2.0,
                generated_event_count=100,
            )

        with tempfile.TemporaryDirectory() as temporary:
            summary = execute_energy_scan(
                expanded,
                point_executor=executor,
                output_directory=temporary,
                scan_id="test_exception",
            )

        self.assertEqual(
            summary.failed_point_count,
            1,
        )
        self.assertIn(
            "RuntimeError",
            (
                summary
                .point_results[0]
                .failure_message
                or ""
            ),
        )

    def test_csv_json_and_plot_are_saved(
        self,
    ) -> None:
        expanded = make_expanded_scan()

        def executor(point):
            return PointExecutionOutcome(
                success=True,
                cross_section_pb=(
                    point.energy_gev
                    / 1000.0
                ),
                cross_section_uncertainty_pb=0.05,
                generated_event_count=100,
                point_record_path=(
                    f"runs/{point.output_name}.json"
                ),
            )

        with tempfile.TemporaryDirectory() as temporary:
            summary = execute_energy_scan(
                expanded,
                point_executor=executor,
                output_directory=temporary,
                scan_id="test_files",
            )

            self.assertTrue(
                Path(summary.csv_path).is_file()
            )
            self.assertTrue(
                Path(summary.json_path).is_file()
            )
            self.assertIsNotNone(
                summary.plot_path
            )

            assert summary.plot_path is not None

            self.assertTrue(
                Path(summary.plot_path).is_file()
            )

            payload = json.loads(
                Path(summary.json_path)
                .read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                payload["scan_id"],
                "test_files",
            )


if __name__ == "__main__":
    unittest.main()
