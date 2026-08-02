"""Tests for validator-guided structured repair."""

import json
import unittest

from hep_agent.models import ModelResponse, repair_workflow
from hep_agent.schemas import (
    BeamSpec,
    ColliderSpec,
    ColliderType,
    EnergyMeaning,
    EnergySpec,
    ParticleNode,
    PhysicsModelSpec,
    PipelineSpec,
    ProcessSpec,
    RunSettings,
    TaskType,
    WorkflowIntent,
)
from hep_agent.validation import validate_request_grounding


REQUEST = (
    "Simulate proton-proton collisions producing an electron and a "
    "positron at a total centre-of-mass energy of 13 TeV. "
    "Generate 10000 events. Do not use Pythia8 or Delphes."
)


def make_workflow(
    incoming: tuple[str, str],
) -> WorkflowIntent:
    return WorkflowIntent(
        task_type=TaskType.RUN_SIMULATION,
        model=PhysicsModelSpec(name="sm"),
        collider=ColliderSpec(
            collider_type=ColliderType.HADRON,
            beams=[
                BeamSpec(particle="p"),
                BeamSpec(particle="p"),
            ],
            energy=EnergySpec(
                value_gev=13_000,
                meaning=EnergyMeaning.TOTAL_CENTER_OF_MASS,
            ),
        ),
        processes=[
            ProcessSpec(
                incoming_particles=list(incoming),
                final_particles=[
                    ParticleNode(particle="e+"),
                    ParticleNode(particle="e-"),
                ],
            )
        ],
        run=RunSettings(nevents=10_000),
        pipeline=PipelineSpec(
            madgraph=True,
            pythia8=False,
            delphes=False,
        ),
    )


class FakeClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.last_request = None

    def chat(self, **kwargs):
        self.last_request = kwargs

        return ModelResponse(
            model=kwargs["model"],
            content=self.content,
            total_duration_ns=1_000_000_000,
        )


class RepairTests(unittest.TestCase):
    def test_repair_corrects_partonic_substitution(self) -> None:
        invalid = make_workflow(("q", "q~"))

        grounding = validate_request_grounding(
            REQUEST,
            invalid,
        )

        corrected = make_workflow(("p", "p"))
        client = FakeClient(
            corrected.model_dump_json()
        )

        result = repair_workflow(
            user_request=REQUEST,
            invalid_workflow=invalid,
            validation_report=grounding.report,
            client=client,
            model="qwen3-coder-next:Q4_K_M",
        )

        self.assertEqual(
            result.workflow.processes[0].incoming_particles,
            ["p", "p"],
        )

    def test_validator_feedback_is_sent_to_model(self) -> None:
        invalid = make_workflow(("q", "q~"))

        grounding = validate_request_grounding(
            REQUEST,
            invalid,
        )

        client = FakeClient(
            make_workflow(("p", "p")).model_dump_json()
        )

        repair_workflow(
            user_request=REQUEST,
            invalid_workflow=invalid,
            validation_report=grounding.report,
            client=client,
            model="qwen3-coder-next:Q4_K_M",
        )

        user_message = client.last_request["messages"][1]["content"]
        payload = json.loads(user_message)

        error_codes = [
            issue["code"]
            for issue in payload["validator_errors"]
        ]

        self.assertIn(
            "explicit_process_incoming_mismatch",
            error_codes,
        )
        self.assertEqual(
            payload["original_user_request"],
            REQUEST,
        )

    def test_repair_uses_structured_schema(self) -> None:
        invalid = make_workflow(("q", "q~"))

        grounding = validate_request_grounding(
            REQUEST,
            invalid,
        )

        client = FakeClient(
            make_workflow(("p", "p")).model_dump_json()
        )

        repair_workflow(
            user_request=REQUEST,
            invalid_workflow=invalid,
            validation_report=grounding.report,
            client=client,
            model="qwen3-coder-next:Q4_K_M",
        )

        self.assertIn(
            "response_schema",
            client.last_request,
        )
        self.assertEqual(
            client.last_request["temperature"],
            0.0,
        )

    def test_repair_without_errors_is_rejected(self) -> None:
        valid = make_workflow(("p", "p"))

        grounding = validate_request_grounding(
            REQUEST,
            valid,
        )

        client = FakeClient(valid.model_dump_json())

        with self.assertRaises(ValueError):
            repair_workflow(
                user_request=REQUEST,
                invalid_workflow=valid,
                validation_report=grounding.report,
                client=client,
                model="qwen3-coder-next:Q4_K_M",
            )


if __name__ == "__main__":
    unittest.main()
