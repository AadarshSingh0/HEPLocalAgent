"""Tests for the structured collider planner."""

import json
import unittest

from hep_agent.models import (
    ModelResponse,
    PlannerError,
    PlannerFailureType,
    parse_planner_content,
    plan_workflow,
)
from hep_agent.schemas import FieldSource


def valid_payload() -> dict:
    return {
        "schema_version": "1.0",
        "task_type": "run_simulation",
        "model": {
            "name": "sm",
            "source": "builtin",
            "model_path": None
        },
        "collider": {
            "collider_type": "hadron",
            "beams": [
                {"particle": "p", "label": None},
                {"particle": "p", "label": None}
            ],
            "energy": {
                "value_gev": 13000,
                "meaning": "total_center_of_mass"
            }
        },
        "processes": [
            {
                "process_id": "dilepton",
                "incoming_particles": ["p", "p"],
                "final_particles": [
                    {
                        "particle": "e-",
                        "branch_id": None,
                        "label": None,
                        "decay_products": []
                    },
                    {
                        "particle": "e+",
                        "branch_id": None,
                        "label": None,
                        "decay_products": []
                    }
                ],
                "required_intermediates": [],
                "excluded_particles": [],
                "coupling_orders": {}
            }
        ],
        "run": {
            "nevents": 10000,
            "random_seed": None,
            "timeout_seconds": 1800,
            "output_name": "dilepton_run"
        },
        "pipeline": {
            "madgraph": True,
            "pythia8": False,
            "delphes": False,
            "madanalysis": False
        },
        "field_sources": {
            "model.name": "user",
            "collider.beams": "user",
            "collider.energy.value_gev": "user",
            "processes": "user"
        },
        "notes": []
    }


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


class PlannerTests(unittest.TestCase):
    def test_valid_content_is_parsed(self) -> None:
        workflow = parse_planner_content(
            json.dumps(valid_payload())
        )

        self.assertEqual(workflow.model.name, "sm")
        self.assertEqual(
            workflow.collider.energy.value_gev,
            13000,
        )

    def test_missing_ordinary_provenance_is_completed(self) -> None:
        workflow = parse_planner_content(
            json.dumps(valid_payload())
        )

        self.assertEqual(
            workflow.field_sources["run.nevents"],
            FieldSource.VALIDATED_DEFAULT,
        )
        self.assertEqual(
            workflow.field_sources["pipeline.pythia8"],
            FieldSource.VALIDATED_DEFAULT,
        )

    def test_missing_physics_provenance_is_conservative(self) -> None:
        payload = valid_payload()
        payload["field_sources"] = {}

        workflow = parse_planner_content(
            json.dumps(payload)
        )

        self.assertEqual(
            workflow.field_sources["processes"],
            FieldSource.MODEL_INFERENCE,
        )

    def test_invalid_json_is_classified(self) -> None:
        with self.assertRaises(PlannerError) as context:
            parse_planner_content("not-json")

        self.assertEqual(
            context.exception.failure_type,
            PlannerFailureType.INVALID_JSON,
        )

    def test_schema_failure_is_classified(self) -> None:
        payload = valid_payload()
        del payload["collider"]

        with self.assertRaises(PlannerError) as context:
            parse_planner_content(json.dumps(payload))

        self.assertEqual(
            context.exception.failure_type,
            PlannerFailureType.SCHEMA_VALIDATION,
        )

    def test_plan_workflow_supplies_json_schema(self) -> None:
        client = FakeClient(
            json.dumps(valid_payload())
        )

        result = plan_workflow(
            "Simulate p p to e- e+ at 13 TeV.",
            client=client,
            model="qwen3-coder-next:Q4_K_M",
        )

        self.assertEqual(
            result.workflow.processes[0]
            .final_particles[0].particle,
            "e-",
        )
        self.assertIn(
            "response_schema",
            client.last_request,
        )
        self.assertEqual(
            client.last_request["temperature"],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
