"""Tests for deterministic analysis-request grounding."""

import unittest

from hep_agent.models import AgentProfile
from hep_agent.orchestration.preexecution import (
    FailureCategory,
    PreExecutionStatus,
    run_preexecution_loop,
)
from hep_agent.schemas import WorkflowIntent
from hep_agent.validation import (
    validate_request_grounding,
)
from hep_agent.validation.analysis_request import (
    extract_analysis_request_facts,
    validate_analysis_request_capability,
    validate_analysis_request_grounding,
)


def make_workflow(
    *,
    analysis: dict | None,
    madanalysis: bool = True,
) -> WorkflowIntent:
    return WorkflowIntent.model_validate(
        {
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
                    "value_gev": 13000,
                    "meaning": "total_center_of_mass"
                }
            },
            "processes": [
                {
                    "incoming_particles": ["p", "p"],
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
                "madanalysis": madanalysis
            },
            "analysis": analysis
        }
    )


HISTOGRAM = {
    "schema_version": "1.0",
    "histograms": [
        {
            "histogram_id": "mass",
            "observable": "invariant_mass",
            "objects": [
                {"particle": "e+", "rank": 1},
                {"particle": "e-", "rank": 1}
            ],
            "unit": "GeV",
            "bins": 40,
            "minimum": 50,
            "maximum": 130
        }
    ],
    "cuts": []
}


class ExplodingClient:
    """Client that proves unsupported requests never call Ollama."""

    def generate(self, *args, **kwargs):
        raise AssertionError(
            "Ollama must not be called."
        )


class AnalysisRequestGroundingTests(
    unittest.TestCase
):
    def test_custom_plot_cannot_disappear(
        self,
    ) -> None:
        request = (
            "Use MadAnalysis to plot the invariant mass "
            "from 50 to 130 GeV with 40 bins."
        )

        report = (
            validate_analysis_request_grounding(
                request,
                make_workflow(
                    analysis=None
                ),
            )
        )

        self.assertFalse(report.is_valid)
        self.assertIn(
            "explicit_custom_plot_missing",
            [
                issue.code
                for issue in report.errors
            ],
        )

    def test_combined_grounding_includes_analysis_issues(
        self,
    ) -> None:
        request = (
            "Simulate proton-proton collisions producing an "
            "electron and a positron at 13 TeV. Generate 100 "
            "events with Pythia8 and no Delphes. Use "
            "MadAnalysis to plot their invariant mass from "
            "50 to 130 GeV with 40 bins and apply standard "
            "cuts."
        )

        result = validate_request_grounding(
            request,
            make_workflow(
                analysis=None
            ),
        )

        self.assertFalse(
            result.report.is_valid
        )
        self.assertIn(
            "explicit_custom_plot_missing",
            [
                issue.code
                for issue in result.report.errors
            ],
        )

    def test_vague_standard_cuts_cannot_gain_numbers(
        self,
    ) -> None:
        analysis = {
            **HISTOGRAM,
            "cuts": [
                {
                    "cut_id": "invented",
                    "observable": "pt",
                    "objects": [
                        {
                            "particle": "e+",
                            "rank": 1
                        }
                    ],
                    "unit": "GeV",
                    "comparison": ">",
                    "value": 20
                }
            ]
        }

        report = (
            validate_analysis_request_grounding(
                (
                    "Use MadAnalysis to plot invariant "
                    "mass and apply standard cuts."
                ),
                make_workflow(
                    analysis=analysis
                ),
            )
        )

        self.assertFalse(report.is_valid)
        self.assertIn(
            "invented_standard_cut_thresholds",
            [
                issue.code
                for issue in report.errors
            ],
        )

    def test_explicit_no_cuts_is_respected(
        self,
    ) -> None:
        report = (
            validate_analysis_request_grounding(
                (
                    "Use MadAnalysis to plot invariant "
                    "mass. Do not apply selection cuts."
                ),
                make_workflow(
                    analysis=HISTOGRAM
                ),
            )
        )

        self.assertTrue(report.is_valid)

    def test_energy_difference_is_unsupported(
        self,
    ) -> None:
        report = (
            validate_analysis_request_capability(
                (
                    "Use MadAnalysis to plot the energy "
                    "difference E(e+) minus E(e-)."
                )
            )
        )

        self.assertFalse(report.is_valid)
        self.assertEqual(
            report.errors[0].code,
            "unsupported_energy_difference",
        )

    def test_cut_only_request_is_unsupported(
        self,
    ) -> None:
        facts = extract_analysis_request_facts(
            (
                "Use MadAnalysis to require both particles "
                "to have pT above 20 GeV, but do not "
                "produce any plots."
            )
        )

        self.assertEqual(
            facts.unsupported_code,
            "unsupported_cut_only_analysis",
        )

    def test_unsupported_request_never_calls_model(
        self,
    ) -> None:
        profile = AgentProfile(
            primary_model="unused",
            fallback_model=None,
            primary_timeout_seconds=1,
            fallback_timeout_seconds=None,
            max_repairs=0,
        )

        result = run_preexecution_loop(
            (
                "Use MadAnalysis to plot the energy "
                "difference E(e+) minus E(e-)."
            ),
            client=ExplodingClient(),
            profile=profile,
        )

        self.assertEqual(
            result.status,
            PreExecutionStatus.BLOCKED,
        )
        self.assertEqual(
            result.failure_category,
            FailureCategory.UNSUPPORTED_REQUEST,
        )
        self.assertEqual(
            result.llm_call_count,
            0,
        )


if __name__ == "__main__":
    unittest.main()
