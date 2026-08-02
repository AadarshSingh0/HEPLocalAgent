"""Tests for deterministic MadGraph result parsing."""

import tempfile
import unittest
from pathlib import Path

from hep_agent.execution import (
    find_primary_lhe_file,
    parse_madgraph_result,
)


STDOUT_SAMPLE = """
  === Results Summary for run: run_01 tag: tag_1 ===

     Cross-section :   845.7 +- 6.244 pb
     Nb of events :  10

Failed to access python version of LHAPDF
"""


class ResultParserTests(unittest.TestCase):
    def test_cross_section_and_events_are_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            lhe = (
                root
                / "process"
                / "Events"
                / "run_01"
                / "unweighted_events.lhe.gz"
            )
            lhe.parent.mkdir(parents=True)
            lhe.write_bytes(b"fake")

            result = parse_madgraph_result(
                stdout_text=STDOUT_SAMPLE,
                execution_directory=root,
            )

            self.assertEqual(
                result.cross_section_pb,
                845.7,
            )
            self.assertEqual(
                result.cross_section_uncertainty_pb,
                6.244,
            )
            self.assertEqual(result.event_count, 10)
            self.assertEqual(result.primary_lhe_file, lhe)
            self.assertTrue(result.has_physics_summary)

    def test_lhapdf_message_is_only_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = parse_madgraph_result(
                stdout_text=STDOUT_SAMPLE,
                execution_directory=temporary,
            )

            self.assertIn(
                "lhapdf_python_interface_unavailable",
                result.warnings,
            )
            self.assertTrue(result.has_physics_summary)

    def test_fb_is_converted_to_pb(self) -> None:
        text = """
        Cross-section : 2500 +- 100 fb
        Nb of events : 50
        """

        with tempfile.TemporaryDirectory() as temporary:
            result = parse_madgraph_result(
                stdout_text=text,
                execution_directory=temporary,
            )

            self.assertEqual(result.cross_section_pb, 2.5)
            self.assertEqual(
                result.cross_section_uncertainty_pb,
                0.1,
            )

    def test_missing_summary_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = parse_madgraph_result(
                stdout_text="MG5 finished without summary",
                execution_directory=temporary,
            )

            self.assertIsNone(result.cross_section_pb)
            self.assertIsNone(result.event_count)
            self.assertFalse(result.has_physics_summary)
            self.assertIn(
                "cross_section_not_found",
                result.warnings,
            )
            self.assertIn(
                "event_count_not_found",
                result.warnings,
            )

    def test_primary_lhe_file_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            expected = (
                root
                / "process"
                / "Events"
                / "run_01"
                / "unweighted_events.lhe.gz"
            )
            expected.parent.mkdir(parents=True)
            expected.write_bytes(b"fake")

            self.assertEqual(
                find_primary_lhe_file(root),
                expected,
            )


if __name__ == "__main__":
    unittest.main()
