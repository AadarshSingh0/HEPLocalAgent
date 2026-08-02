"""Tests for the complete pre-execution agent loop."""

import json
import unittest

from hep_agent.models import (
    AgentProfile,
    ModelFailureType,
    ModelResponse,
    OllamaClientError,
)
from hep_agent.orchestration import (
    ApprovalDecision,
    FailureCategory,
    PreExecutionStatus,
    run_preexecution_loop,
)


REQUEST = (
    "Simulate proton-proton collisions producing an electron and a "
    "positron at a total centre-of-mass energy of 13 TeV. "
    "Generate 10000 events. Do not use Pythia8 or Delphes."
)


def payload(
    *,
    incoming: tuple[str, str] = ("p", "p"),
    final: tuple[str, str] = ("e-", "e+"),
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
                "process_id": "process_1",
                "incoming_particles": list(incoming),
                "final_particles": [
                    {
                        "particle": final[0],
                        "decay_products": [],
                    },
                    {
                        "particle": final[1],
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


class SequenceClient:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.models: list[str] = []

    def chat(self, **kwargs):
        self.models.append(kwargs["model"])

        if not self.responses:
            raise AssertionError("No fake response remains.")

        response = self.responses.pop(0)

        return ModelResponse(
            model=kwargs["model"],
            content=json.dumps(response),
            total_duration_ns=1_000_000_000,
        )


class FailingClient:
    def chat(self, **kwargs):
        raise OllamaClientError(
            "connection failed",
            failure_type=ModelFailureType.CONNECTION,
        )


class PreExecutionTests(unittest.TestCase):
    def test_deterministic_correction_avoids_repair_call(self) -> None:
        client = SequenceClient([
            payload(incoming=("q", "q~")),
        ])

        profile = AgentProfile(
            primary_model="qwen",
            primary_timeout_seconds=180,
            max_repairs=2,
        )

        result = run_preexecution_loop(
            REQUEST,
            client=client,
            profile=profile,
        )

        self.assertEqual(
            result.status,
            PreExecutionStatus.READY_FOR_APPROVAL,
        )
        self.assertEqual(result.llm_call_count, 1)
        self.assertEqual(result.repair_attempts, 0)
        self.assertEqual(
            result.workflow.processes[0].incoming_particles,
            ["p", "p"],
        )
        self.assertEqual(
            result.approval.decision,
            ApprovalDecision.AUTO_CONFIRM,
        )

    def test_model_repair_requires_explicit_confirmation(self) -> None:
        client = SequenceClient([
            payload(final=("mu-", "mu+")),
            payload(final=("e-", "e+")),
        ])

        profile = AgentProfile(
            primary_model="qwen",
            primary_timeout_seconds=180,
            max_repairs=1,
        )

        result = run_preexecution_loop(
            REQUEST,
            client=client,
            profile=profile,
        )

        self.assertTrue(result.is_ready)
        self.assertEqual(result.llm_call_count, 2)
        self.assertEqual(result.repair_attempts, 1)
        self.assertEqual(
            result.approval.decision,
            ApprovalDecision.EXPLICIT_CONFIRMATION,
        )

    def test_fallback_is_used_after_primary_repair_fails(self) -> None:
        client = SequenceClient([
            payload(final=("mu-", "mu+")),
            payload(final=("mu-", "mu+")),
            payload(final=("e-", "e+")),
        ])

        profile = AgentProfile(
            primary_model="qwen",
            fallback_model="llama70b",
            primary_timeout_seconds=180,
            fallback_timeout_seconds=600,
            max_repairs=1,
        )

        result = run_preexecution_loop(
            REQUEST,
            client=client,
            profile=profile,
        )

        self.assertTrue(result.is_ready)
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.llm_call_count, 3)
        self.assertEqual(
            client.models,
            ["qwen", "qwen", "llama70b"],
        )

    def test_model_connection_failure_is_not_semantic_failure(
        self,
    ) -> None:
        profile = AgentProfile(
            primary_model="qwen",
            primary_timeout_seconds=180,
        )

        result = run_preexecution_loop(
            REQUEST,
            client=FailingClient(),
            profile=profile,
        )

        self.assertEqual(
            result.status,
            PreExecutionStatus.FAILED,
        )
        self.assertEqual(
            result.failure_category,
            FailureCategory.MODEL_INFRASTRUCTURE,
        )
        self.assertEqual(
            result.llm_call_count,
            2,
        )

        self.assertEqual(
            [
                call.role
                for call in result.model_calls
            ],
            [
                "planner_infrastructure_failure",
                (
                    "planner_retry_2_"
                    "infrastructure_failure"
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
