"""Tests for the deterministic installation self-test.

The real toolchain (MadGraph/Pythia8/Delphes/MadAnalysis) is not available in
CI, so these tests mock the execution and analysis stages and verify the
per-tool reporting logic. The workflow-construction test needs no tools.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hep_agent.builders import build_madgraph_workflow_artifact
from hep_agent.selftest import (
    build_selftest_workflow,
    run_installation_selftest,
)


class SelfTestWorkflowTests(unittest.TestCase):
    def test_all_stages_enabled(self) -> None:
        workflow = build_selftest_workflow(nevents=500)
        self.assertTrue(workflow.pipeline.madgraph)
        self.assertTrue(workflow.pipeline.pythia8)
        self.assertTrue(workflow.pipeline.delphes)
        self.assertTrue(workflow.pipeline.madanalysis)

    def test_artifact_requests_shower_and_detector(self) -> None:
        artifact = build_madgraph_workflow_artifact(
            build_selftest_workflow(nevents=500)
        )
        self.assertIn("shower=Pythia8", artifact.text)
        self.assertIn("detector=Delphes", artifact.text)
        self.assertIn("generate p p > e+ e-", artifact.text)


def _patch(module_attr, value):
    return mock.patch(f"hep_agent.selftest.{module_attr}", value)


class SelfTestReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        base = Path(self._dir.name)
        self.stdout = base / "stdout.log"
        self.stdout.write_text("MG5 output")
        self.lhe = base / "events.lhe"
        self.lhe.write_text("lhe")
        self.hepmc = base / "events.hepmc"
        self.hepmc.write_text("hepmc")
        self.root = base / "delphes.root"
        self.root.write_text("root")

    def tearDown(self) -> None:
        self._dir.cleanup()

    def _run(self, *, execution, physics, valid, analysis):
        with _patch(
            "run_madgraph_workflow", lambda *a, **k: execution
        ), _patch(
            "parse_madgraph_result", lambda *a, **k: physics
        ), _patch(
            "execution_has_valid_physics_output", lambda *a, **k: valid
        ), _patch(
            "run_madanalysis_stage", lambda *a, **k: analysis
        ):
            return run_installation_selftest(
                mg5_executable="/fake/mg5",
                madanalysis_executable="/fake/ma5",
                nevents=500,
                run_directory=self._dir.name,
            )

    def test_all_tools_pass(self) -> None:
        execution = SimpleNamespace(
            success=True, stdout_path=self.stdout, failure_message=None
        )
        physics = SimpleNamespace(
            primary_lhe_file=self.lhe,
            showered_hepmc_file=self.hepmc,
            detector_root_file=self.root,
            cross_section_pb=1.23,
            event_count=500,
        )
        analysis = SimpleNamespace(success=True, failure_message=None)

        result = self._run(
            execution=execution,
            physics=physics,
            valid=True,
            analysis=analysis,
        )

        self.assertTrue(result.success)
        self.assertEqual(
            {s.name: s.ok for s in result.stages},
            {
                "MadGraph": True,
                "Pythia8": True,
                "Delphes": True,
                "MadAnalysis": True,
            },
        )
        self.assertEqual(result.cross_section_pb, 1.23)

    def test_madgraph_failure_fails_all(self) -> None:
        execution = SimpleNamespace(
            success=False,
            stdout_path=None,
            failure_message="mg5 executable not found",
        )

        result = self._run(
            execution=execution,
            physics=None,
            valid=False,
            analysis=None,
        )

        self.assertFalse(result.success)
        stages = {s.name: s.ok for s in result.stages}
        self.assertFalse(stages["MadGraph"])
        self.assertFalse(stages["Pythia8"])
        self.assertFalse(stages["Delphes"])
        self.assertFalse(stages["MadAnalysis"])

    def test_missing_pythia_output_fails_pythia_only(self) -> None:
        execution = SimpleNamespace(
            success=True, stdout_path=self.stdout, failure_message=None
        )
        physics = SimpleNamespace(
            primary_lhe_file=self.lhe,
            showered_hepmc_file=None,  # Pythia produced nothing
            detector_root_file=self.root,
            cross_section_pb=1.0,
            event_count=500,
        )
        analysis = SimpleNamespace(success=True, failure_message=None)

        result = self._run(
            execution=execution,
            physics=physics,
            valid=True,
            analysis=analysis,
        )

        self.assertFalse(result.success)
        stages = {s.name: s.ok for s in result.stages}
        self.assertTrue(stages["MadGraph"])
        self.assertFalse(stages["Pythia8"])
        self.assertTrue(stages["Delphes"])

    def test_madanalysis_failure_reported(self) -> None:
        execution = SimpleNamespace(
            success=True, stdout_path=self.stdout, failure_message=None
        )
        physics = SimpleNamespace(
            primary_lhe_file=self.lhe,
            showered_hepmc_file=self.hepmc,
            detector_root_file=self.root,
            cross_section_pb=1.0,
            event_count=500,
        )
        analysis = SimpleNamespace(
            success=False, failure_message="MA5 executable not configured"
        )

        result = self._run(
            execution=execution,
            physics=physics,
            valid=True,
            analysis=analysis,
        )

        self.assertFalse(result.success)
        stages = {s.name: s.ok for s in result.stages}
        self.assertTrue(stages["MadGraph"])
        self.assertFalse(stages["MadAnalysis"])


if __name__ == "__main__":
    unittest.main()
