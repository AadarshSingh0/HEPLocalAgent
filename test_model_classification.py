"""Tests for tolerant built-in model classification in the planner parser."""

from __future__ import annotations

import json
import unittest

from hep_agent.models.planner import PlannerError, parse_planner_content
from hep_agent.schemas import ModelSource


def payload(*, name, source, model_path=None):
    """Build a raw planner JSON payload with a given model classification."""

    model = {"name": name, "source": source}
    if model_path is not None:
        model["model_path"] = model_path

    return json.dumps(
        {
            "task_type": "run_simulation",
            "model": model,
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
                    "incoming_particles": ["p", "p"],
                    "final_particles": [
                        {"particle": "t"},
                        {"particle": "t~"},
                    ],
                }
            ],
            "run": {"nevents": 100},
            "pipeline": {
                "madgraph": True,
                "pythia8": False,
                "delphes": False,
                "madanalysis": False,
            },
        }
    )


class ModelClassificationTests(unittest.TestCase):
    def test_standardmodel_user_ufo_is_repaired(self) -> None:
        # The reproduced failure: 'StandardModel' + user_ufo with no path.
        workflow = parse_planner_content(
            payload(name="StandardModel", source="user_ufo")
        )

        self.assertEqual(workflow.model.name, "sm")
        self.assertEqual(workflow.model.source, ModelSource.BUILTIN)
        self.assertIsNone(workflow.model.model_path)

    def test_spelling_variants_normalise_to_sm(self) -> None:
        for spelling in [
            "sm",
            "SM",
            "Standard Model",
            "standard_model",
            "Standard-Model",
            "  StandardModel  ",
        ]:
            with self.subTest(spelling=spelling):
                workflow = parse_planner_content(
                    payload(name=spelling, source="user_ufo")
                )
                self.assertEqual(workflow.model.name, "sm")
                self.assertEqual(
                    workflow.model.source, ModelSource.BUILTIN
                )

    def test_loop_sm_variants_normalise(self) -> None:
        for spelling in ["loop_sm", "loopsm", "LOOP_SM"]:
            with self.subTest(spelling=spelling):
                workflow = parse_planner_content(
                    payload(name=spelling, source="builtin")
                )
                self.assertEqual(workflow.model.name, "loop_sm")
                self.assertEqual(
                    workflow.model.source, ModelSource.BUILTIN
                )

    def test_builtin_sm_spelling_is_normalised_even_when_source_ok(
        self,
    ) -> None:
        # Name spelled oddly but already builtin -> name still canonicalised.
        workflow = parse_planner_content(
            payload(name="StandardModel", source="builtin")
        )
        self.assertEqual(workflow.model.name, "sm")

    def test_genuine_user_ufo_with_path_is_untouched(self) -> None:
        # An unrecognised model name is a real UFO and must not be rewritten.
        workflow = parse_planner_content(
            payload(
                name="MyBSM",
                source="user_ufo",
                model_path="/models/MyBSM",
            )
        )
        self.assertEqual(workflow.model.name, "MyBSM")
        self.assertEqual(workflow.model.source, ModelSource.USER_UFO)
        self.assertEqual(workflow.model.model_path, "/models/MyBSM")

    def test_unknown_model_without_path_still_fails(self) -> None:
        # We only rescue recognised built-ins; an unknown user_ufo without a
        # path is still a genuine error (fixed later by retry feedback, not by
        # inventing a model). This documents the boundary.
        with self.assertRaises(PlannerError):
            parse_planner_content(
                payload(name="TotallyUnknownModel", source="user_ufo")
            )


if __name__ == "__main__":
    unittest.main()
