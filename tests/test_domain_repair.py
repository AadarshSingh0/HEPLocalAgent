"""Tests that model-domain violations are repairable, not just blocking.

An invalid particle token (e.g. the glued ``tt~``) produced by the planner
should be fed back to the repair model with its suggested correction. If the
repair succeeds the workflow proceeds; if it never succeeds, the final artifact
validation still blocks execution so containment is preserved.
"""

from __future__ import annotations

import json
import unittest

from hep_agent.models import AgentProfile, ModelResponse
from hep_agent.orchestration import (
    PreExecutionStatus,
    run_preexecution_loop,
)


# A request with no explicit final-state particles, so grounding stays silent
# on the particle and only the domain validator catches ``tt~``.
REQUEST = (
    "Simulate proton-proton collisions at a total centre-of-mass energy "
    "of 13 TeV. Generate 100 events. Do not use Pythia8 or Delphes."
)


def payload(final_particles: list[str]) -> dict:
    return {
        "schema_version": "1.0",
        "task_type": "run_simulation",
        "model": {"name": "sm", "source": "builtin", "model_path": None},
        "collider": {
            "collider_type": "hadron",
            "beams": [{"particle": "p"}, {"particle": "p"}],
            "energy": {
                "value_gev": 13000,
                "meaning": "total_center_of_mass",
            },
        },
        "processes": [
            {
                "process_id": "process_1",
                "incoming_particles": ["p", "p"],
                "final_particles": [
                    {"particle": particle, "decay_products": []}
                    for particle in final_particles
                ],
                "required_intermediates": [],
                "excluded_particles": [],
                "coupling_orders": {},
            }
        ],
        "run": {
            "nevents": 100,
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


class DomainRepairTests(unittest.TestCase):
    def test_invalid_particle_is_repaired(self) -> None:
        # Planner emits the glued token; repair returns the split form.
        client = SequenceClient([
            payload(["tt~"]),
            payload(["t", "t~"]),
        ])
        profile = AgentProfile(
            primary_model="qwen",
            primary_timeout_seconds=180,
            max_repairs=2,
        )

        result = run_preexecution_loop(
            REQUEST, client=client, profile=profile
        )

        self.assertEqual(
            result.status, PreExecutionStatus.READY_FOR_APPROVAL
        )
        self.assertGreaterEqual(result.repair_attempts, 1)
        finals = [
            node.particle
            for node in result.workflow.processes[0].final_particles
        ]
        self.assertEqual(finals, ["t", "t~"])

    def test_unrepaired_invalid_particle_is_blocked(self) -> None:
        # Planner and every repair keep emitting the invalid token: the loop
        # must never reach approval or execution.
        client = SequenceClient([
            payload(["tt~"]),
            payload(["tt~"]),
            payload(["tt~"]),
        ])
        profile = AgentProfile(
            primary_model="qwen",
            primary_timeout_seconds=180,
            max_repairs=2,
        )

        result = run_preexecution_loop(
            REQUEST, client=client, profile=profile
        )

        self.assertNotEqual(
            result.status, PreExecutionStatus.READY_FOR_APPROVAL
        )

    def test_valid_particles_do_not_trigger_domain_repair(self) -> None:
        # Regression: a correct workflow is accepted with no repair.
        client = SequenceClient([payload(["t", "t~"])])
        profile = AgentProfile(
            primary_model="qwen",
            primary_timeout_seconds=180,
            max_repairs=2,
        )

        result = run_preexecution_loop(
            REQUEST, client=client, profile=profile
        )

        self.assertEqual(
            result.status, PreExecutionStatus.READY_FOR_APPROVAL
        )
        self.assertEqual(result.repair_attempts, 0)


if __name__ == "__main__":
    unittest.main()
