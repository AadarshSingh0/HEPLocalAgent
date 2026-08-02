"""Tests for deterministic pre-execution evaluation checks."""

import unittest
from types import SimpleNamespace

from hep_agent.evaluation import (
    evaluate_prepared_scenario,
)
from hep_agent.schemas import (
    WorkflowIntent,
)


def make_workflow(
    *,
    pt_value: float = 35.0,
) -> WorkflowIntent:
    return WorkflowIntent.model_validate(
        {
            "schema_version": "1.0",
            "task_type": "run_simulation",
            "model": {
                "name": "sm",
                "source": "builtin"
            },
            "collider": {
                "collider_type": "hadron",
                "beams": [
                    {"particle": "p"},
                    {"particle": "p"}
                ],
                "energy": {
                    "value_gev": 13600.0,
                    "meaning": "total_center_of_mass"
                }
            },
            "processes": [
                {
                    "process_id": "dilepton",
                    "incoming_particles": [
                        "p",
                        "p"
                    ],
                    "final_particles": [
                        {"particle": "e+"},
                        {"particle": "e-"}
                    ]
                }
            ],
            "run": {
                "nevents": 100
            },
            "pipeline": {
                "madgraph": True,
                "pythia8": True,
                "delphes": False,
                "madanalysis": True
            },
            "analysis": {
                "schema_version": "1.0",
                "histograms": [
                    {
                        "histogram_id": "mass",
                        "observable": "invariant_mass",
                        "objects": [
                            {
                                "particle": "e+",
                                "rank": 1
                            },
                            {
                                "particle": "e-",
                                "rank": 1
                            }
                        ],
                        "unit": "GeV",
                        "bins": 20,
                        "minimum": 70.0,
                        "maximum": 110.0
                    }
                ],
                "cuts": [
                    {
                        "cut_id": "pt_plus",
                        "observable": "pt",
                        "objects": [
                            {
                                "particle": "e+",
                                "rank": 1
                            }
                        ],
                        "unit": "GeV",
                        "comparison": ">",
                        "value": pt_value
                    }
                ]
            }
        }
    )


def make_prepared(
    workflow: WorkflowIntent | None,
    *,
    ready: bool,
):
    return SimpleNamespace(
        is_ready=ready,
        result=SimpleNamespace(
            workflow=workflow
        ),
    )


SCENARIO = {
    "id": "TEST",
    "expected": {
        "ready": True,
        "energy_gev": 13600.0,
        "nevents": 100,
        "pipeline": {
            "madgraph": True,
            "pythia8": True,
            "delphes": False,
            "madanalysis": True
        },
        "analysis": {
            "mode": "custom",
            "exact_histogram_count": 1,
            "exact_cut_count": 1,
            "histograms": [
                {
                    "observable": "invariant_mass",
                    "particles": ["e+", "e-"],
                    "bins": 20,
                    "minimum": 70.0,
                    "maximum": 110.0,
                    "unit": "GeV"
                }
            ],
            "cuts": [
                {
                    "observable": "pt",
                    "particles": ["e+"],
                    "comparison": ">",
                    "value": 35.0,
                    "unit": "GeV"
                }
            ]
        }
    }
}


class PreExecutionEvaluationTests(
    unittest.TestCase
):
    def test_exact_structured_workflow_passes(
        self,
    ) -> None:
        result = evaluate_prepared_scenario(
            make_prepared(
                make_workflow(),
                ready=True,
            ),
            SCENARIO,
        )

        self.assertTrue(result.passed)

    def test_changed_cut_value_fails(
        self,
    ) -> None:
        result = evaluate_prepared_scenario(
            make_prepared(
                make_workflow(
                    pt_value=40.0
                ),
                ready=True,
            ),
            SCENARIO,
        )

        self.assertFalse(result.passed)
        self.assertIn(
            "expected_cut_1",
            [
                check.name
                for check in result.checks
                if not check.passed
            ],
        )

    def test_expected_safe_rejection_passes(
        self,
    ) -> None:
        scenario = {
            "id": "BLOCKED",
            "expected": {
                "ready": False
            }
        }

        result = evaluate_prepared_scenario(
            make_prepared(
                None,
                ready=False,
            ),
            scenario,
        )

        self.assertTrue(result.passed)

    def test_unexpected_ready_state_fails(
        self,
    ) -> None:
        scenario = {
            "id": "BLOCKED",
            "expected": {
                "ready": False
            }
        }

        result = evaluate_prepared_scenario(
            make_prepared(
                make_workflow(),
                ready=True,
            ),
            scenario,
        )

        self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()
