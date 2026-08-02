"""Tests for structured-analysis planner integration."""

import json
import unittest

from hep_agent.models import (
    ModelResponse,
    load_planner_prompt,
    parse_planner_content,
    plan_workflow,
)
from hep_agent.schemas import (
    AnalysisCutSpec,
    AnalysisHistogramSpec,
    AnalysisObservable,
    FieldSource,
)


def base_payload() -> dict:
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
                {
                    "particle": "p",
                    "label": None,
                },
                {
                    "particle": "p",
                    "label": None,
                },
            ],
            "energy": {
                "value_gev": 13000,
                "meaning": (
                    "total_center_of_mass"
                ),
            },
        },
        "processes": [
            {
                "process_id": "dilepton",
                "incoming_particles": [
                    "p",
                    "p",
                ],
                "final_particles": [
                    {
                        "particle": "e+",
                        "branch_id": None,
                        "label": None,
                        "decay_products": [],
                    },
                    {
                        "particle": "e-",
                        "branch_id": None,
                        "label": None,
                        "decay_products": [],
                    },
                ],
                "required_intermediates": [],
                "excluded_particles": [],
                "coupling_orders": {},
            }
        ],
        "run": {
            "nevents": 100,
            "random_seed": 42,
            "timeout_seconds": 1800,
            "output_name": "dilepton",
        },
        "pipeline": {
            "madgraph": True,
            "pythia8": True,
            "delphes": False,
            "madanalysis": True,
        },
        "analysis": None,
        "field_sources": {},
        "notes": [],
    }


def custom_analysis_payload() -> dict:
    payload = base_payload()

    payload["analysis"] = {
        "schema_version": "1.0",
        "cuts": [
            {
                "cut_id": "positron_pt",
                "observable": "pt",
                "objects": [
                    {
                        "particle": "e+",
                        "rank": 1,
                    }
                ],
                "comparison": ">",
                "value": 20,
                "unit": "GeV",
            },
            {
                "cut_id": "electron_pt",
                "observable": "pt",
                "objects": [
                    {
                        "particle": "e-",
                        "rank": 1,
                    }
                ],
                "comparison": ">",
                "value": 20,
                "unit": "GeV",
            },
        ],
        "histograms": [
            {
                "histogram_id": (
                    "dilepton_mass"
                ),
                "observable": (
                    "invariant_mass"
                ),
                "objects": [
                    {
                        "particle": "e+",
                        "rank": 1,
                    },
                    {
                        "particle": "e-",
                        "rank": 1,
                    },
                ],
                "bins": 30,
                "minimum": 60,
                "maximum": 120,
                "unit": "GeV",
            }
        ],
    }

    return payload


class FakeClient:
    def __init__(
        self,
        content: str,
    ) -> None:
        self.content = content
        self.last_request = None

    def chat(self, **kwargs):
        self.last_request = kwargs

        return ModelResponse(
            model=kwargs["model"],
            content=self.content,
            total_duration_ns=1_000_000,
        )


class PlannerAnalysisTests(
    unittest.TestCase
):
    def test_quicklook_keeps_analysis_null(
        self,
    ) -> None:
        workflow = parse_planner_content(
            json.dumps(base_payload())
        )

        self.assertTrue(
            workflow.pipeline.madanalysis
        )
        self.assertIsNone(
            workflow.analysis
        )

    def test_custom_analysis_is_parsed(
        self,
    ) -> None:
        workflow = parse_planner_content(
            json.dumps(
                custom_analysis_payload()
            )
        )

        self.assertIsNotNone(
            workflow.analysis
        )

        assert workflow.analysis is not None

        self.assertEqual(
            workflow.analysis
            .histograms[0]
            .observable,
            AnalysisObservable.INVARIANT_MASS,
        )

        self.assertEqual(
            len(workflow.analysis.cuts),
            2,
        )

    def test_missing_analysis_provenance_is_conservative(
        self,
    ) -> None:
        workflow = parse_planner_content(
            json.dumps(
                custom_analysis_payload()
            )
        )

        self.assertEqual(
            workflow.field_sources[
                "analysis"
            ],
            FieldSource.MODEL_INFERENCE,
        )

    def test_explicit_analysis_provenance_is_preserved(
        self,
    ) -> None:
        payload = custom_analysis_payload()

        payload["field_sources"][
            "analysis"
        ] = "user"

        workflow = parse_planner_content(
            json.dumps(payload)
        )

        self.assertEqual(
            workflow.field_sources[
                "analysis"
            ],
            FieldSource.USER,
        )

    def test_planner_schema_contains_analysis(
        self,
    ) -> None:
        client = FakeClient(
            json.dumps(
                custom_analysis_payload()
            )
        )

        result = plan_workflow(
            (
                "Plot the dilepton mass from "
                "60 to 120 GeV."
            ),
            client=client,
            model=(
                "qwen3-coder-next:Q4_K_M"
            ),
        )

        self.assertIsNotNone(
            result.workflow.analysis
        )

        schema = client.last_request[
            "response_schema"
        ]

        self.assertIn(
            "analysis",
            schema["properties"],
        )

    def test_analysis_objects_are_required_by_schema(
        self,
    ) -> None:
        histogram_schema = (
            AnalysisHistogramSpec
            .model_json_schema()
        )
        cut_schema = (
            AnalysisCutSpec
            .model_json_schema()
        )

        self.assertIn(
            "objects",
            histogram_schema["required"],
        )
        self.assertIn(
            "objects",
            cut_schema["required"],
        )

    def test_prompt_contains_no_invented_cut_policy(
        self,
    ) -> None:
        prompt = load_planner_prompt()

        self.assertIn(
            (
                "Never invent \"standard cuts\""
            ),
            prompt,
        )
        self.assertIn(
            (
                "Set analysis to null"
            ),
            prompt,
        )


if __name__ == "__main__":
    unittest.main()
