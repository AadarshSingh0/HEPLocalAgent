"""Tests for reproducible pre-execution run records."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from hep_agent.models import (
    AgentProfile,
    ModelFailureType,
    ModelResponse,
    OllamaClientError,
)
from hep_agent.orchestration import (
    FailureCategory,
    run_preexecution_and_record,
)
from hep_agent.models.semantic_process import (
    SEMANTIC_PROCESS_PROMPT,
)


REQUEST = (
    "Simulate proton-proton collisions producing an electron and a "
    "positron at a total centre-of-mass energy of 13 TeV. "
    "Generate 10000 events. Do not use Pythia8 or Delphes."
)


def payload() -> dict:
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
                "process_id": "process_1",
                "incoming_particles": ["q", "q~"],
                "final_particles": [
                    {
                        "particle": "e-",
                        "decay_products": [],
                    },
                    {
                        "particle": "e+",
                        "decay_products": [],
                    },
                ],
                "required_intermediates": [],
                "excluded_particles": [],
                "coupling_orders": {},
            }
        ],
        "run": {
            "nevents": 10000,
            "random_seed": None,
            "timeout_seconds": 1800,
            "output_name": None,
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


class SuccessfulClient:
    def chat(self, **kwargs):
        return ModelResponse(
            model=kwargs["model"],
            content=json.dumps(payload()),
            total_duration_ns=2_000_000_000,
        )


class FailingClient:
    def chat(self, **kwargs):
        raise OllamaClientError(
            "connection failed",
            failure_type=ModelFailureType.CONNECTION,
        )


class RunRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = AgentProfile(
            primary_model="qwen",
            primary_timeout_seconds=180,
            max_repairs=2,
        )

    def test_successful_record_is_saved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorded = run_preexecution_and_record(
                REQUEST,
                client=SuccessfulClient(),
                profile_name="test_profile",
                profile=self.profile,
                output_directory=directory,
            )

            self.assertTrue(recorded.record_path.exists())

            saved = json.loads(
                recorded.record_path.read_text(
                    encoding="utf-8"
                )
            )

            self.assertTrue(
                saved["final_preexecution_success"]
            )
            self.assertEqual(saved["llm_call_count"], 1)
            self.assertEqual(saved["corrections_applied"], 1)
            self.assertFalse(
                saved["first_attempt_grounding_success"]
            )
            self.assertEqual(
                saved["model_generation_time_seconds"],
                2.0,
            )
            self.assertEqual(
                saved["approval"]["auto_confirm_delay_seconds"],
                5,
            )

    def test_record_contains_reproducibility_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorded = run_preexecution_and_record(
                REQUEST,
                client=SuccessfulClient(),
                profile_name="test_profile",
                profile=self.profile,
                output_directory=directory,
            )

            record = recorded.record

            self.assertEqual(len(record.profile_sha256), 64)
            self.assertEqual(
                len(record.planner_prompt_sha256),
                64,
            )
            self.assertEqual(
                len(record.repair_prompt_sha256),
                64,
            )
            self.assertEqual(
                record.semantic_prompt_sha256,
                hashlib.sha256(
                    SEMANTIC_PROCESS_PROMPT.encode(
                        "utf-8"
                    )
                ).hexdigest(),
            )

    def test_infrastructure_failure_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorded = run_preexecution_and_record(
                REQUEST,
                client=FailingClient(),
                profile_name="test_profile",
                profile=self.profile,
                output_directory=directory,
            )

            self.assertFalse(
                recorded.record.final_preexecution_success
            )
            self.assertEqual(
                recorded.record.failure_category,
                FailureCategory.MODEL_INFRASTRUCTURE.value,
            )
            self.assertEqual(
                recorded.record.llm_call_count,
                2,
            )
            self.assertTrue(
                recorded.record_path.exists()
            )


    def test_record_file_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorded = run_preexecution_and_record(
                REQUEST,
                client=SuccessfulClient(),
                profile_name="test_profile",
                profile=self.profile,
                output_directory=directory,
            )

            parsed = json.loads(
                Path(recorded.record_path).read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                parsed["record_version"],
                "1.1",
            )


if __name__ == "__main__":
    unittest.main()
