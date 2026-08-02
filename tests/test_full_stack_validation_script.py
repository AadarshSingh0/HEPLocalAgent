"""Tests for the model-free installed-tool validation utility."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hep_agent.models import AgentProfile
from hep_agent.orchestration import prepare_end_to_end
from scripts.validate_full_stack import (
    FixedValidationPlanner,
    build_payload,
    build_request,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_full_stack.py"


class FullStackValidationScriptTests(unittest.TestCase):
    def test_help_is_available_without_installed_hep_tools(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        for tool in (
            "MadGraph",
            "Pythia8",
            "Delphes",
            "MadAnalysis",
        ):
            self.assertIn(tool, completed.stdout)
        self.assertIn("--events", completed.stdout)

    def test_invalid_configuration_is_reported_cleanly(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--paths-config",
                str(ROOT / "configs" / "does-not-exist.json"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn(
            "Configuration error:",
            completed.stderr,
        )

    def test_fixed_workflow_is_grounded_and_ready(self) -> None:
        events = 20
        payload = build_payload(
            events=events,
            timeout_seconds=3600,
        )
        profile = AgentProfile(
            primary_model="fixed-full-stack-validation",
            primary_timeout_seconds=30,
            max_repairs=0,
            max_planner_attempts=1,
        )

        with tempfile.TemporaryDirectory() as temporary:
            prepared = prepare_end_to_end(
                build_request(events),
                client=FixedValidationPlanner(payload),
                profile_name="full_stack_validation_test",
                profile=profile,
                records_directory=Path(temporary),
            )

        self.assertTrue(
            prepared.is_ready,
            prepared.result,
        )
        workflow = prepared.result.workflow
        self.assertIsNotNone(workflow)
        self.assertTrue(workflow.pipeline.madgraph)
        self.assertTrue(workflow.pipeline.pythia8)
        self.assertTrue(workflow.pipeline.delphes)
        self.assertTrue(workflow.pipeline.madanalysis)


if __name__ == "__main__":
    unittest.main()
