"""Tests for the full agent through external execution."""

import json
import tempfile
import unittest
from pathlib import Path

from hep_agent.models import AgentProfile, ModelResponse
from hep_agent.orchestration import (
    EndToEndStatus,
    run_end_to_end,
)


REQUEST = (
    "Simulate proton-proton collisions producing an electron and a "
    "positron at a total centre-of-mass energy of 13 TeV. "
    "Generate 10 events. Do not use Pythia8 or Delphes."
)

PYTHIA_REQUEST = (
    "Simulate proton-proton collisions producing an electron and a "
    "positron at a total centre-of-mass energy of 13 TeV. "
    "Generate 10 events with Pythia8 and without Delphes."
)

DELPHES_REQUEST = (
    "Simulate proton-proton collisions producing an electron and a "
    "positron at a total centre-of-mass energy of 13 TeV. "
    "Generate 10 events with Pythia8 and Delphes."
)


def planner_payload(
    *,
    pythia8: bool = False,
    delphes: bool = False,
) -> dict:
    return {
        "schema_version": "1.0",
        "task_type": "run_simulation",
        "model": {
            "name": "sm",
            "source": "builtin",
            "model_path": None,
        },
        "collider": {
            "collider_type": "hadron",
            "beams": [
                {"particle": "p"},
                {"particle": "p"},
            ],
            "energy": {
                "value_gev": 13000,
                "meaning": "total_center_of_mass",
            },
        },
        "processes": [
            {
                "process_id": "dilepton",
                "incoming_particles": ["p", "p"],
                "final_particles": [
                    {
                        "particle": "e+",
                        "decay_products": [],
                    },
                    {
                        "particle": "e-",
                        "decay_products": [],
                    },
                ],
                "required_intermediates": [],
                "excluded_particles": [],
                "coupling_orders": {},
            }
        ],
        "run": {
            "nevents": 10,
            "random_seed": 1,
            "timeout_seconds": 30,
            "output_name": "test_process",
        },
        "pipeline": {
            "madgraph": True,
            "pythia8": pythia8,
            "delphes": delphes,
            "madanalysis": False,
        },
        "field_sources": {},
        "notes": [],
    }


class FakeClient:
    def __init__(
        self,
        *,
        pythia8: bool = False,
        delphes: bool = False,
    ) -> None:
        self.pythia8 = pythia8
        self.delphes = delphes

    def chat(self, **kwargs):
        return ModelResponse(
            model=kwargs["model"],
            content=json.dumps(
                planner_payload(
                    pythia8=self.pythia8,
                    delphes=self.delphes,
                )
            ),
            total_duration_ns=1_000_000_000,
        )


def make_fake_mg5(
    root: Path,
    *,
    returncode: int = 0,
    write_lhe: bool = True,
    write_hepmc: bool = False,
    write_root: bool = False,
) -> Path:
    path = root / "fake_mg5.py"

    body = f'''#!/usr/bin/env python3
from pathlib import Path
import sys

run_root = Path.cwd()
events = (
    run_root
    / "test_process"
    / "Events"
    / "run_01"
)
events.mkdir(parents=True, exist_ok=True)

if {write_lhe!r}:
    (events / "unweighted_events.lhe.gz").write_bytes(b"fake")

if {write_hepmc!r}:
    (events / "tag_1_pythia8_events.hepmc.gz").write_bytes(b"fake")

if {write_root!r}:
    (events / "tag_1_delphes_events.root").write_bytes(b"fake")

print("Cross-section : 12.5 +- 0.5 pb")
print("Nb of events : 10")

raise SystemExit({returncode})
'''

    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


class EndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = AgentProfile(
            primary_model="qwen",
            primary_timeout_seconds=30,
            max_repairs=1,
        )

    def test_successful_end_to_end_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = make_fake_mg5(root)

            observed = []

            result = run_end_to_end(
                REQUEST,
                client=FakeClient(),
                profile_name="test",
                profile=self.profile,
                mg5_executable=executable,
                approval_resolver=lambda approval: True,
                preexecution_observer=observed.append,
                records_directory=root / "records",
                executions_directory=root / "executions",
                project_root=root,
            )

            self.assertTrue(result.success)
            self.assertEqual(len(observed), 1)
            self.assertTrue(observed[0].is_ready)
            self.assertEqual(
                result.status,
                EndToEndStatus.COMPLETED,
            )
            self.assertTrue(
                result.final_record.execution_success
            )
            self.assertEqual(
                result.final_record.cross_section_pb,
                12.5,
            )
            self.assertEqual(
                result.final_record.generated_event_count,
                10,
            )
            self.assertNotIn(
                str(root),
                result.final_record.primary_lhe_file,
            )

    def test_cancelled_run_does_not_execute(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = make_fake_mg5(root)

            result = run_end_to_end(
                REQUEST,
                client=FakeClient(),
                profile_name="test",
                profile=self.profile,
                mg5_executable=executable,
                approval_resolver=lambda approval: False,
                records_directory=root / "records",
                executions_directory=root / "executions",
                project_root=root,
            )

            self.assertEqual(
                result.status,
                EndToEndStatus.CANCELLED,
            )
            self.assertFalse(
                result.final_record.execution_started
            )
            self.assertFalse(
                result.final_record.approval_obtained
            )

    def test_nonzero_execution_is_classified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = make_fake_mg5(
                root,
                returncode=7,
            )

            result = run_end_to_end(
                REQUEST,
                client=FakeClient(),
                profile_name="test",
                profile=self.profile,
                mg5_executable=executable,
                approval_resolver=lambda approval: True,
                records_directory=root / "records",
                executions_directory=root / "executions",
                project_root=root,
            )

            self.assertEqual(
                result.status,
                EndToEndStatus.EXECUTION_FAILED,
            )
            self.assertFalse(
                result.final_record.execution_success
            )
            self.assertEqual(
                result.final_record
                .execution_failure_category,
                "nonzero_exit",
            )

    def test_missing_lhe_fails_normal_execution(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_end_to_end(
                REQUEST,
                client=FakeClient(),
                profile_name="test",
                profile=self.profile,
                mg5_executable=make_fake_mg5(
                    root,
                    write_lhe=False,
                ),
                approval_resolver=lambda approval: True,
                records_directory=root / "records",
                executions_directory=root / "executions",
                project_root=root,
            )

            self.assertEqual(
                result.status,
                EndToEndStatus.EXECUTION_FAILED,
            )
            self.assertEqual(
                result.final_record.missing_requested_outputs,
                ["parton_level_lhe"],
            )
            self.assertIn(
                "requested_output_not_found:parton_level_lhe",
                result.final_record.execution_warnings,
            )

    def test_requested_pythia_requires_hepmc(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_end_to_end(
                PYTHIA_REQUEST,
                client=FakeClient(pythia8=True),
                profile_name="test",
                profile=self.profile,
                mg5_executable=make_fake_mg5(root),
                approval_resolver=lambda approval: True,
                records_directory=root / "records",
                executions_directory=root / "executions",
                project_root=root,
            )

            self.assertEqual(
                result.status,
                EndToEndStatus.EXECUTION_FAILED,
            )
            self.assertEqual(
                result.final_record.missing_requested_outputs,
                ["showered_hepmc"],
            )

    def test_requested_delphes_requires_root(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_end_to_end(
                DELPHES_REQUEST,
                client=FakeClient(
                    pythia8=True,
                    delphes=True,
                ),
                profile_name="test",
                profile=self.profile,
                mg5_executable=make_fake_mg5(
                    root,
                    write_hepmc=True,
                ),
                approval_resolver=lambda approval: True,
                records_directory=root / "records",
                executions_directory=root / "executions",
                project_root=root,
            )

            self.assertEqual(
                result.status,
                EndToEndStatus.EXECUTION_FAILED,
            )
            self.assertEqual(
                result.final_record.missing_requested_outputs,
                ["detector_root"],
            )

    def test_all_requested_stage_outputs_complete(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_end_to_end(
                DELPHES_REQUEST,
                client=FakeClient(
                    pythia8=True,
                    delphes=True,
                ),
                profile_name="test",
                profile=self.profile,
                mg5_executable=make_fake_mg5(
                    root,
                    write_hepmc=True,
                    write_root=True,
                ),
                approval_resolver=lambda approval: True,
                records_directory=root / "records",
                executions_directory=root / "executions",
                project_root=root,
            )

            self.assertEqual(
                result.status,
                EndToEndStatus.COMPLETED,
            )
            self.assertEqual(
                result.final_record.missing_requested_outputs,
                [],
            )


if __name__ == "__main__":
    unittest.main()
