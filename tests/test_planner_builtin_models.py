"""Regression tests for recognised built-in model normalisation."""

import json
import unittest

from hep_agent.models import parse_planner_content


class PlannerBuiltinModelTests(unittest.TestCase):
    def test_sm_misclassified_as_user_ufo_is_corrected(self) -> None:
        payload = {
            "schema_version": "1.0",
            "task_type": "run_simulation",
            "model": {
                "name": "SM",
                "source": "user_ufo",
                "model_path": None
            },
            "collider": {
                "collider_type": "hadron",
                "beams": [
                    {"particle": "p"},
                    {"particle": "p"}
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
                            "decay_products": []
                        },
                        {
                            "particle": "e+",
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
                "timeout_seconds": 1800
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
                "processes": "user",
                "run.nevents": "user",
                "pipeline.pythia8": "user",
                "pipeline.delphes": "user"
            },
            "notes": []
        }

        workflow = parse_planner_content(json.dumps(payload))

        self.assertEqual(workflow.model.name, "sm")
        self.assertEqual(workflow.model.source.value, "builtin")
        self.assertIsNone(workflow.model.model_path)


if __name__ == "__main__":
    unittest.main()
