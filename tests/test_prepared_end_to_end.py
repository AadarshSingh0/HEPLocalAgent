"""Tests for separately preparing and executing one workflow."""

import json
import tempfile
import unittest
from pathlib import Path

from hep_agent.models import (
    AgentProfile,
    ModelResponse,
)
from hep_agent.orchestration import (
    EndToEndStatus,
    execute_prepared,
    prepare_end_to_end,
)


REQUEST = (
    "Simulate proton-proton collisions producing an electron "
    "and a positron at 13 TeV. Generate 10 events."
)


def planner_payload() -> dict:
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
            "output_name": "hep_agent_output",
        },
        "pipeline": {
            "madgraph": True,
            "pythia8": False,
            "delphes": False,
            "madanalysis": False,
        },
        "field_sources": {},
        "notes": [],
    }


class CountingClient:
    """Synthetic planner client that counts model calls."""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1

        return ModelResponse(
            model=kwargs["model"],
            content=json.dumps(
                planner_payload()
            ),
            total_duration_ns=1_000_000,
        )


def make_fake_mg5(root: Path) -> Path:
    """Create a synthetic executable producing one LHE file."""

    executable = root / "fake_mg5.py"

    executable.write_text(
        '''#!/usr/bin/env python3
from pathlib import Path

lhe = (
    Path.cwd()
    / "hep_agent_output"
    / "Events"
    / "run_01"
    / "unweighted_events.lhe.gz"
)

lhe.parent.mkdir(
    parents=True,
    exist_ok=True,
)
lhe.write_bytes(b"synthetic LHE")

print("Cross-section : 12.5 +- 0.5 pb")
print("Nb of events : 10")
''',
        encoding="utf-8",
    )

    executable.chmod(0o755)

    return executable


class PreparedEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = AgentProfile(
            primary_model="qwen",
            primary_timeout_seconds=30,
            max_repairs=1,
        )

    def test_prepare_does_not_execute_madgraph(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            client = CountingClient()

            prepared = prepare_end_to_end(
                REQUEST,
                client=client,
                profile_name="test",
                profile=self.profile,
                records_directory=root / "records",
            )

            self.assertTrue(prepared.is_ready)
            self.assertEqual(client.calls, 1)
            self.assertFalse(
                (root / "executions").exists()
            )

    def test_execution_does_not_call_planner_again(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            client = CountingClient()

            prepared = prepare_end_to_end(
                REQUEST,
                client=client,
                profile_name="test",
                profile=self.profile,
                records_directory=root / "records",
            )

            self.assertEqual(client.calls, 1)

            result = execute_prepared(
                prepared,
                approved=True,
                mg5_executable=make_fake_mg5(root),
                records_directory=root / "records",
                executions_directory=root / "executions",
                analyses_directory=root / "analyses",
                project_root=root,
                unsupported_nonhermetic=True,
            )

            self.assertEqual(client.calls, 1)
            self.assertEqual(
                result.status,
                EndToEndStatus.COMPLETED,
            )
            self.assertTrue(result.success)
            self.assertTrue(
                result.final_record.execution_success
            )

    def test_cancelled_prepared_run_does_not_execute(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            client = CountingClient()

            prepared = prepare_end_to_end(
                REQUEST,
                client=client,
                profile_name="test",
                profile=self.profile,
                records_directory=root / "records",
            )

            result = execute_prepared(
                prepared,
                approved=False,
                mg5_executable=root / "missing_mg5",
                records_directory=root / "records",
                executions_directory=root / "executions",
                analyses_directory=root / "analyses",
                project_root=root,
                unsupported_nonhermetic=True,
            )

            self.assertEqual(client.calls, 1)
            self.assertEqual(
                result.status,
                EndToEndStatus.CANCELLED,
            )
            self.assertIsNone(result.execution)
            self.assertFalse(
                (root / "executions").exists()
            )


if __name__ == "__main__":
    unittest.main()
