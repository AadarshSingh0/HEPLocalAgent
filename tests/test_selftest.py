"""Tests for the tool-aware installation self-test.

The real toolchain is not available in CI, so these tests build a fake
MadGraph tree (so tool detection is exercised for real) and mock the execution
and analysis stages to verify the per-tool reporting logic.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hep_agent.builders import build_madgraph_workflow_artifact
from hep_agent.selftest import (
    _diagnose_from_log,
    build_selftest_workflow,
    detect_tools,
    run_installation_selftest,
)


def make_mg5_tree(base, *, pythia=True, delphes=True, madanalysis=True):
    """Create a fake MadGraph tree and return its bin/mg5_aMC path."""

    (base / "bin").mkdir(parents=True, exist_ok=True)
    mg5 = base / "bin" / "mg5_aMC"
    mg5.write_text("#!/bin/sh\n")
    heptools = base / "HEPTools"
    heptools.mkdir(parents=True, exist_ok=True)
    if pythia:
        (heptools / "pythia8").mkdir()
    if delphes:
        (heptools / "Delphes").mkdir()
    if madanalysis:
        (heptools / "madanalysis5").mkdir()
    return mg5


def _patch(name, value):
    return mock.patch(f"hep_agent.selftest.{name}", value)


class DetectionTests(unittest.TestCase):
    def test_detects_present_tools(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mg5 = make_mg5_tree(Path(d), pythia=True, delphes=True)
            detected = detect_tools(mg5)
            self.assertTrue(detected["pythia8"])
            self.assertTrue(detected["delphes"])
            self.assertTrue(detected["heptools_found"])

    def test_detects_missing_delphes(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mg5 = make_mg5_tree(Path(d), pythia=True, delphes=False)
            detected = detect_tools(mg5)
            self.assertTrue(detected["pythia8"])
            self.assertFalse(detected["delphes"])


class WorkflowTests(unittest.TestCase):
    def test_stage_flags_flow_into_pipeline(self) -> None:
        wf = build_selftest_workflow(delphes=False)
        self.assertTrue(wf.pipeline.pythia8)
        self.assertFalse(wf.pipeline.delphes)
        art = build_madgraph_workflow_artifact(wf)
        self.assertIn("shower=Pythia8", art.text)
        self.assertNotIn("detector=Delphes", art.text)


class ReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        base = Path(self._dir.name)
        self.tree = base / "mg5tree"
        out = base / "out"
        out.mkdir(parents=True, exist_ok=True)
        self.stdout = out / "stdout.log"
        self.stdout.write_text("MG5")
        self.lhe = out / "events.lhe"
        self.lhe.write_text("lhe")
        self.hepmc = out / "events.hepmc"
        self.hepmc.write_text("hepmc")
        self.root = out / "delphes.root"
        self.root.write_text("root")
        self.ma5 = base / "ma5"
        self.ma5.write_text("#!/bin/sh\n")

    def tearDown(self) -> None:
        self._dir.cleanup()

    def _run(self, mg5, *, execution, physics, valid, analysis, **kw):
        with _patch("run_madgraph_workflow", lambda *a, **k: execution), \
             _patch("parse_madgraph_result", lambda *a, **k: physics), \
             _patch("execution_has_valid_physics_output",
                    lambda *a, **k: valid), \
             _patch("run_madanalysis_stage", lambda *a, **k: analysis):
            return run_installation_selftest(
                mg5_executable=str(mg5),
                madanalysis_executable=str(self.ma5),
                nevents=100,
                run_directory=self._dir.name,
                **kw,
            )

    def _good_physics(self, *, hepmc=True, root=True):
        return SimpleNamespace(
            primary_lhe_file=self.lhe,
            showered_hepmc_file=self.hepmc if hepmc else None,
            detector_root_file=self.root if root else None,
            cross_section_pb=835.1,
            event_count=100,
        )

    def test_all_present_all_pass(self) -> None:
        mg5 = make_mg5_tree(self.tree, pythia=True, delphes=True)
        result = self._run(
            mg5,
            execution=SimpleNamespace(
                success=True, stdout_path=self.stdout, failure_message=None
            ),
            physics=self._good_physics(),
            valid=True,
            analysis=SimpleNamespace(success=True, failure_message=None),
        )
        self.assertTrue(result.success)
        self.assertEqual(
            {s.name: s.status for s in result.stages},
            {
                "MadGraph": "ok",
                "Pythia8": "ok",
                "Delphes": "ok",
                "MadAnalysis": "ok",
            },
        )

    def test_missing_delphes_is_warning_not_failure(self) -> None:
        # Delphes absent from the tree: reported missing, Pythia still tested,
        # overall still a pass. This is the real user scenario.
        mg5 = make_mg5_tree(self.tree, pythia=True, delphes=False)
        result = self._run(
            mg5,
            execution=SimpleNamespace(
                success=True, stdout_path=self.stdout, failure_message=None
            ),
            physics=self._good_physics(root=False),
            valid=True,
            analysis=SimpleNamespace(success=True, failure_message=None),
        )
        status = {s.name: s.status for s in result.stages}
        self.assertEqual(status["MadGraph"], "ok")
        self.assertEqual(status["Pythia8"], "ok")
        self.assertEqual(status["Delphes"], "missing")
        self.assertEqual(status["MadAnalysis"], "ok")
        self.assertTrue(result.success)
        self.assertEqual(result.missing, ["Delphes"])

    def test_madgraph_failure_fails_overall(self) -> None:
        mg5 = make_mg5_tree(self.tree, pythia=True, delphes=True)
        result = self._run(
            mg5,
            execution=SimpleNamespace(
                success=False, stdout_path=None,
                failure_message="mg5 crashed",
            ),
            physics=None,
            valid=False,
            analysis=None,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.stages[0].status, "failed")

    def test_installed_pythia_without_output_fails(self) -> None:
        mg5 = make_mg5_tree(self.tree, pythia=True, delphes=False)
        result = self._run(
            mg5,
            execution=SimpleNamespace(
                success=True, stdout_path=self.stdout, failure_message=None
            ),
            physics=self._good_physics(hepmc=False, root=False),
            valid=True,
            analysis=SimpleNamespace(success=True, failure_message=None),
        )
        status = {s.name: s.status for s in result.stages}
        self.assertEqual(status["Pythia8"], "failed")
        self.assertFalse(result.success)

    def test_force_off_skips_stage(self) -> None:
        mg5 = make_mg5_tree(self.tree, pythia=True, delphes=True)
        result = self._run(
            mg5,
            execution=SimpleNamespace(
                success=True, stdout_path=self.stdout, failure_message=None
            ),
            physics=self._good_physics(),
            valid=True,
            analysis=SimpleNamespace(success=True, failure_message=None),
            delphes="off",
        )
        status = {s.name: s.status for s in result.stages}
        self.assertEqual(status["Delphes"], "skipped")
        self.assertTrue(result.success)


    def test_pythia_failure_includes_log_diagnosis(self) -> None:
        # The real user case: version mismatch + segfault -> shower disabled.
        self.stdout.write_text(
            "RuntimeWarning: compiletime version 3.8 of module "
            "'python.lhapdf' does not match runtime version 3.12\n"
            "Segmentation fault (core dumped)\n"
        )
        mg5 = make_mg5_tree(self.tree, pythia=True, delphes=False)
        result = self._run(
            mg5,
            execution=SimpleNamespace(
                success=True, stdout_path=self.stdout, failure_message=None
            ),
            physics=self._good_physics(hepmc=False, root=False),
            valid=True,
            analysis=SimpleNamespace(success=True, failure_message=None),
        )
        pythia = next(s for s in result.stages if s.name == "Pythia8")
        self.assertEqual(pythia.status, "failed")
        self.assertIn("Likely cause", pythia.detail)
        self.assertIn("3.8", pythia.detail)


class DiagnosisTests(unittest.TestCase):
    def test_version_mismatch_is_diagnosed(self) -> None:
        diagnosis = _diagnose_from_log(
            "RuntimeWarning: compiletime version 3.8 of module "
            "'python.lhapdf' does not match runtime version 3.12"
        )
        self.assertIsNotNone(diagnosis)
        self.assertIn("3.8", diagnosis)
        self.assertIn("3.12", diagnosis)

    def test_segfault_is_diagnosed(self) -> None:
        diagnosis = _diagnose_from_log("Segmentation fault (core dumped)")
        self.assertIsNotNone(diagnosis)
        self.assertIn("segmentation fault", diagnosis.lower())

    def test_shower_off_is_diagnosed(self) -> None:
        diagnosis = _diagnose_from_log(
            "| 1. Choose the shower program   shower = OFF   |"
        )
        self.assertIsNotNone(diagnosis)
        self.assertIn("shower", diagnosis.lower())

    def test_clean_log_has_no_diagnosis(self) -> None:
        self.assertIsNone(
            _diagnose_from_log("Events generated successfully.")
        )


if __name__ == "__main__":
    unittest.main()
