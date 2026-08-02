"""Tests for deterministic natural-language energy-scan parsing."""

import unittest

from hep_agent.scans import (
    EnergyScanTextError,
    generate_energy_grid,
    parse_energy_scan_text,
)


class EnergyScanTextParserTests(unittest.TestCase):
    def test_steps_of_phrase_is_parsed(
        self,
    ) -> None:
        parsed = parse_energy_scan_text(
            "Simulate p p to e+ e-. Do an energy scan "
            "from 1 TeV to 5 TeV in steps of 500 GeV. "
            "Generate 100 events per point."
        )

        self.assertIsNotNone(parsed)

        assert parsed is not None

        self.assertEqual(
            generate_energy_grid(
                parsed.energy_range
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

    def test_distance_phrase_is_parsed(
        self,
    ) -> None:
        parsed = parse_energy_scan_text(
            "Run an energy scan from 1 TeV to 5 TeV "
            "at a distance of 500 GeV."
        )

        self.assertIsNotNone(parsed)

        assert parsed is not None

        self.assertEqual(
            parsed.point_count,
            9,
        )

    def test_value_before_steps_is_parsed(
        self,
    ) -> None:
        parsed = parse_energy_scan_text(
            "Scan the collider energy from 1 TeV "
            "to 2 TeV in 250 GeV steps."
        )

        self.assertIsNotNone(parsed)

        assert parsed is not None

        self.assertEqual(
            parsed.point_count,
            5,
        )

    def test_every_phrase_is_parsed(
        self,
    ) -> None:
        parsed = parse_energy_scan_text(
            "Sweep the energy from 1 TeV to 2 TeV "
            "every 250 GeV."
        )

        self.assertIsNotNone(parsed)

        assert parsed is not None

        self.assertEqual(
            parsed.point_count,
            5,
        )

    def test_between_phrase_is_parsed(
        self,
    ) -> None:
        parsed = parse_energy_scan_text(
            "Perform an energy scan between 1 TeV "
            "and 2 TeV in increments of 250 GeV."
        )

        self.assertIsNotNone(parsed)

        assert parsed is not None

        self.assertEqual(
            generate_energy_grid(
                parsed.energy_range
            ),
            [
                1000.0,
                1250.0,
                1500.0,
                1750.0,
                2000.0,
            ],
        )

    def test_single_energy_request_is_not_a_scan(
        self,
    ) -> None:
        parsed = parse_energy_scan_text(
            "Simulate proton collisions at 13 TeV."
        )

        self.assertIsNone(parsed)

    def test_base_request_uses_start_energy(
        self,
    ) -> None:
        parsed = parse_energy_scan_text(
            "Simulate p p to e+ e- and perform an energy "
            "scan from 1 TeV to 5 TeV in steps of 500 GeV. "
            "Generate 100 events."
        )

        self.assertIsNotNone(parsed)

        assert parsed is not None

        self.assertIn(
            "at a total centre-of-mass energy of 1 TEV",
            parsed.base_request,
        )
        self.assertNotIn(
            "5 TeV",
            parsed.base_request,
        )
        self.assertNotIn(
            "500 GeV",
            parsed.base_request,
        )

    def test_boundary_whitespace_is_irrelevant(
        self,
    ) -> None:
        request = (
            "Scan the energy from 1 TeV to 2 TeV "
            "in steps of 500 GeV."
        )

        first = parse_energy_scan_text(request)
        second = parse_energy_scan_text(
            "\n   " + request + "       \n"
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)

        assert first is not None
        assert second is not None

        self.assertEqual(
            first.energy_range,
            second.energy_range,
        )
        self.assertEqual(
            first.base_request,
            second.base_request,
        )

    def test_scan_without_step_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            EnergyScanTextError
        ):
            parse_energy_scan_text(
                "Perform an energy scan from "
                "1 TeV to 5 TeV."
            )

    def test_irregular_endpoint_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            EnergyScanTextError
        ):
            parse_energy_scan_text(
                "Perform an energy scan from 1 TeV "
                "to 2 TeV in steps of 300 GeV."
            )


if __name__ == "__main__":
    unittest.main()
