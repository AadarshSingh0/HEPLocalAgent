"""Tests for unit-safe deterministic energy-scan ranges."""

import unittest

from pydantic import ValidationError

from hep_agent.scans import (
    EnergyQuantity,
    EnergyRangeSpec,
    EnergyScanRequest,
    build_energy_scan_plan_from_range,
    generate_energy_grid,
)

from test_energy_scan import make_workflow


class EnergyScanRangeTests(unittest.TestCase):
    def test_mixed_tev_and_gev_units(self) -> None:
        energy_range = EnergyRangeSpec(
            start=EnergyQuantity(
                value=1,
                unit="TeV",
            ),
            stop=EnergyQuantity(
                value=5,
                unit="tev",
            ),
            step=EnergyQuantity(
                value=500,
                unit="GeV",
            ),
        )

        self.assertEqual(
            generate_energy_grid(
                energy_range
            ),
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

    def test_expected_point_count_is_nine(
        self,
    ) -> None:
        energy_range = EnergyRangeSpec(
            start={
                "value": 1,
                "unit": "tev",
            },
            stop={
                "value": 5,
                "unit": "tev",
            },
            step={
                "value": 500,
                "unit": "gev",
            },
        )

        self.assertEqual(
            energy_range.expected_point_count,
            9,
        )

    def test_inclusive_endpoint_is_present(
        self,
    ) -> None:
        energy_range = EnergyRangeSpec(
            start={
                "value": 1,
                "unit": "tev",
            },
            stop={
                "value": 2,
                "unit": "tev",
            },
            step={
                "value": 250,
                "unit": "gev",
            },
            include_stop=True,
        )

        self.assertEqual(
            generate_energy_grid(
                energy_range
            )[-1],
            2000.0,
        )

    def test_exclusive_endpoint_is_absent(
        self,
    ) -> None:
        energy_range = EnergyRangeSpec(
            start={
                "value": 1,
                "unit": "tev",
            },
            stop={
                "value": 2,
                "unit": "tev",
            },
            step={
                "value": 250,
                "unit": "gev",
            },
            include_stop=False,
        )

        self.assertEqual(
            generate_energy_grid(
                energy_range
            ),
            [
                1000.0,
                1250.0,
                1500.0,
                1750.0,
            ],
        )

    def test_nonintegral_inclusive_endpoint_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValidationError
        ):
            EnergyRangeSpec(
                start={
                    "value": 1,
                    "unit": "tev",
                },
                stop={
                    "value": 2,
                    "unit": "tev",
                },
                step={
                    "value": 300,
                    "unit": "gev",
                },
                include_stop=True,
            )

    def test_descending_range_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValidationError
        ):
            EnergyRangeSpec(
                start={
                    "value": 5,
                    "unit": "tev",
                },
                stop={
                    "value": 1,
                    "unit": "tev",
                },
                step={
                    "value": 500,
                    "unit": "gev",
                },
            )

    def test_scan_point_limit_is_enforced(
        self,
    ) -> None:
        with self.assertRaises(
            ValidationError
        ):
            EnergyRangeSpec(
                start={
                    "value": 1,
                    "unit": "gev",
                },
                stop={
                    "value": 100,
                    "unit": "gev",
                },
                step={
                    "value": 1,
                    "unit": "gev",
                },
            )

    def test_range_builds_complete_scan_plan(
        self,
    ) -> None:
        request = EnergyScanRequest(
            base_workflow=make_workflow(
                nevents=100
            ),
            energy_range={
                "start": {
                    "value": 1,
                    "unit": "tev",
                },
                "stop": {
                    "value": 5,
                    "unit": "tev",
                },
                "step": {
                    "value": 500,
                    "unit": "gev",
                },
            },
        )

        plan = (
            build_energy_scan_plan_from_range(
                request
            )
        )

        self.assertEqual(
            plan.energy_points_gev,
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

        self.assertEqual(
            (
                len(plan.energy_points_gev)
                * plan.base_workflow.run.nevents
            ),
            900,
        )


if __name__ == "__main__":
    unittest.main()
