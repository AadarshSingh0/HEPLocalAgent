"""Regression tests for explicit MadAnalysis negation."""

import unittest

from hep_agent.schemas import (
    WorkflowIntent,
)
from hep_agent.validation.analysis_request import (
    extract_analysis_request_facts,
    validate_analysis_request_grounding,
)


def make_workflow(
    *,
    madanalysis: bool,
) -> WorkflowIntent:
    return WorkflowIntent.model_validate(
        {
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
                    },
                    {
                        "particle": "p",
                    },
                ],
                "energy": {
                    "value_gev": 13000.0,
                    "meaning": (
                        "total_center_of_mass"
                    ),
                },
            },
            "processes": [
                {
                    "process_id": "process_001",
                    "incoming_particles": [
                        "p",
                        "p",
                    ],
                    "final_particles": [
                        {
                            "particle": "e+",
                        },
                        {
                            "particle": "e-",
                        },
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
                "madanalysis": madanalysis,
            },
            "analysis": None,
        }
    )


class MadAnalysisNegationTests(
    unittest.TestCase
):
    def test_do_not_use_is_negative(
        self,
    ) -> None:
        facts = extract_analysis_request_facts(
            (
                "Simulate p p > e+ e- at "
                "13 TeV with 100 events. "
                "Do not use Pythia8, Delphes, "
                "or MadAnalysis."
            )
        )

        self.assertIs(
            facts.madanalysis_choice,
            False,
        )

        self.assertFalse(
            facts.madanalysis_mentioned
        )

    def test_without_is_negative(
        self,
    ) -> None:
        facts = extract_analysis_request_facts(
            (
                "Generate 100 events without "
                "MadAnalysis."
            )
        )

        self.assertIs(
            facts.madanalysis_choice,
            False,
        )

    def test_positive_request_is_positive(
        self,
    ) -> None:
        facts = extract_analysis_request_facts(
            (
                "Use MadAnalysis to plot the "
                "electron-positron invariant mass."
            )
        )

        self.assertIs(
            facts.madanalysis_choice,
            True,
        )

        self.assertTrue(
            facts.madanalysis_mentioned
        )

    def test_no_mention_is_unspecified(
        self,
    ) -> None:
        facts = extract_analysis_request_facts(
            (
                "Simulate p p > e+ e- at "
                "13 TeV with 100 events."
            )
        )

        self.assertIsNone(
            facts.madanalysis_choice
        )

    def test_disabled_workflow_is_valid(
        self,
    ) -> None:
        request = (
            "Simulate p p > e+ e- at "
            "13 TeV with 100 events. "
            "Do not use Pythia8, Delphes, "
            "or MadAnalysis."
        )

        report = (
            validate_analysis_request_grounding(
                request,
                make_workflow(
                    madanalysis=False
                ),
            )
        )

        self.assertTrue(
            report.is_valid
        )

    def test_enabled_workflow_violates_negation(
        self,
    ) -> None:
        request = (
            "Simulate p p > e+ e- at "
            "13 TeV with 100 events. "
            "Do not use Pythia8, Delphes, "
            "or MadAnalysis."
        )

        report = (
            validate_analysis_request_grounding(
                request,
                make_workflow(
                    madanalysis=True
                ),
            )
        )

        self.assertFalse(
            report.is_valid
        )

        self.assertIn(
            (
                "explicit_madanalysis_"
                "choice_mismatch"
            ),
            {
                issue.code
                for issue in report.errors
            },
        )


if __name__ == "__main__":
    unittest.main()
