"""Tests for LHE, HepMC, and Delphes ROOT discovery."""

import tempfile
import unittest
from pathlib import Path

from hep_agent.execution import (
    find_detector_root_file,
    find_showered_hepmc_file,
    parse_madgraph_result,
)


class EventOutputLevelTests(unittest.TestCase):
    def test_pythia8_hepmc_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            expected = (
                root
                / "process"
                / "Events"
                / "run_01"
                / "tag_1_pythia8_events.hepmc.gz"
            )
            expected.parent.mkdir(parents=True)
            expected.write_bytes(b"hepmc")

            self.assertEqual(
                find_showered_hepmc_file(root),
                expected,
            )

    def test_delphes_root_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            expected = (
                root
                / "process"
                / "Events"
                / "run_01"
                / "tag_1_delphes_events.root"
            )
            expected.parent.mkdir(parents=True)
            expected.write_bytes(b"root")

            self.assertEqual(
                find_detector_root_file(root),
                expected,
            )

    def test_parser_records_all_output_levels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = (
                root
                / "process"
                / "Events"
                / "run_01"
            )
            events.mkdir(parents=True)

            lhe = events / "unweighted_events.lhe.gz"
            hepmc = (
                events
                / "tag_1_pythia8_events.hepmc.gz"
            )
            detector = (
                events
                / "tag_1_delphes_events.root"
            )

            lhe.write_bytes(b"lhe")
            hepmc.write_bytes(b"hepmc")
            detector.write_bytes(b"root")

            result = parse_madgraph_result(
                stdout_text=(
                    "Cross-section : 10.0 +- 0.2 pb\n"
                    "Nb of events : 10\n"
                ),
                execution_directory=root,
            )

            self.assertEqual(
                result.primary_lhe_file,
                lhe,
            )
            self.assertEqual(
                result.showered_hepmc_file,
                hepmc,
            )
            self.assertEqual(
                result.detector_root_file,
                detector,
            )
            self.assertTrue(result.has_shower_output)
            self.assertTrue(result.has_detector_output)


if __name__ == "__main__":
    unittest.main()
