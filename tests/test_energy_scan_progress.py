"""Tests for energy-scan progress callbacks."""

import tempfile
import unittest

from hep_agent.scans import (
    PointExecutionOutcome,
    execute_energy_scan,
)

from test_energy_scan_execution import (
    make_expanded_scan,
)


class EnergyScanProgressTests(
    unittest.TestCase
):
    def test_observer_receives_each_point(
        self,
    ) -> None:
        expanded = make_expanded_scan()
        observations = []

        def executor(point):
            return PointExecutionOutcome(
                success=True,
                cross_section_pb=(
                    point.energy_gev / 1000.0
                ),
                generated_event_count=100,
            )

        def observer(
            point_result,
            completed,
            total,
        ):
            observations.append(
                (
                    point_result.index,
                    completed,
                    total,
                )
            )

        with tempfile.TemporaryDirectory() as temporary:
            execute_energy_scan(
                expanded,
                point_executor=executor,
                output_directory=temporary,
                scan_id="progress_test",
                point_observer=observer,
            )

        self.assertEqual(
            observations,
            [
                (0, 1, 3),
                (1, 2, 3),
                (2, 3, 3),
            ],
        )


if __name__ == "__main__":
    unittest.main()
