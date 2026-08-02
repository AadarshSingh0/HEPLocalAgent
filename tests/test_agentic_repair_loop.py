"""Tests for bounded repair retries and larger-model escalation."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hep_agent.models import (
    AgentProfile,
    ModelResponse,
    PlannerError,
    PlannerFailureType,
)
from hep_agent.orchestration.preexecution import (
    PreExecutionStatus,
    run_preexecution_loop,
)
from hep_agent.schemas import WorkflowIntent


REQUEST = (
    "Simulate proton-proton collisions producing an electron "
    "and a positron at 13 TeV. Generate 100 events with "
    "Pythia8 and no Delphes. Use MadAnalysis to plot their "
    "invariant mass from 50 to 130 GeV with 40 bins and "
    "apply standard cuts."
)


def make_workflow(
    *,
    with_analysis: bool,
) -> WorkflowIntent:
    analysis = None

    if with_analysis:
        analysis = {
            "schema_version": "1.0",
            "histograms": [
                {
                    "histogram_id": "ee_mass",
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
                    "bins": 40,
                    "minimum": 50.0,
                    "maximum": 130.0
                }
            ],
            "cuts": []
        }

    return WorkflowIntent.model_validate(
        {
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
                    {"particle": "p"},
                    {"particle": "p"}
                ],
                "energy": {
                    "value_gev": 13000.0,
                    "meaning": (
                        "total_center_of_mass"
                    )
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
                "nevents": 100,
                "random_seed": 42,
                "timeout_seconds": 1800,
                "output_name": "agentic_test"
            },
            "pipeline": {
                "madgraph": True,
                "pythia8": True,
                "delphes": False,
                "madanalysis": True
            },
            "analysis": analysis
        }
    )


def model_result(
    workflow: WorkflowIntent,
    *,
    model: str,
):
    return SimpleNamespace(
        workflow=workflow,
        model_response=ModelResponse(
            model=model,
            content="{}",
            total_duration_ns=1_000_000_000,
        ),
    )


def schema_failure() -> PlannerError:
    return PlannerError(
        (
            "The planner JSON failed schema validation: "
            "observable pt requires exactly one object."
        ),
        failure_type=(
            PlannerFailureType.SCHEMA_VALIDATION
        ),
        raw_content="{}",
    )


class AgenticRepairLoopTests(
    unittest.TestCase
):
    @patch(
        "hep_agent.orchestration."
        "preexecution.repair_workflow"
    )
    @patch(
        "hep_agent.orchestration."
        "preexecution.plan_workflow"
    )
    def test_second_primary_attempt_recovers(
        self,
        mock_plan,
        mock_repair,
    ) -> None:
        mock_plan.return_value = model_result(
            make_workflow(
                with_analysis=False
            ),
            model="small",
        )

        mock_repair.side_effect = [
            schema_failure(),
            model_result(
                make_workflow(
                    with_analysis=True
                ),
                model="small",
            ),
        ]

        profile = AgentProfile(
            primary_model="small",
            fallback_model=None,
            primary_timeout_seconds=10,
            fallback_timeout_seconds=None,
            max_repairs=2,
        )

        result = run_preexecution_loop(
            REQUEST,
            client=object(),
            profile=profile,
        )

        self.assertEqual(
            result.status,
            PreExecutionStatus.READY_FOR_APPROVAL,
        )
        self.assertEqual(
            result.repair_attempts,
            2,
        )
        self.assertFalse(
            result.fallback_used
        )
        self.assertEqual(
            result.llm_call_count,
            3,
        )
        self.assertEqual(
            [
                call.role
                for call in result.model_calls
            ],
            [
                "planner",
                (
                    "primary_repair_1_"
                    "schema_failure"
                ),
                "primary_repair_2",
            ],
        )

        second_feedback = (
            mock_repair.call_args_list[
                1
            ].kwargs[
                "validation_report"
            ]
        )

        self.assertIn(
            "previous_repair_output_invalid",
            [
                issue.code
                for issue
                in second_feedback.issues
            ],
        )

    @patch(
        "hep_agent.orchestration."
        "preexecution.repair_workflow"
    )
    @patch(
        "hep_agent.orchestration."
        "preexecution.plan_workflow"
    )
    def test_larger_fallback_recovers(
        self,
        mock_plan,
        mock_repair,
    ) -> None:
        mock_plan.return_value = model_result(
            make_workflow(
                with_analysis=False
            ),
            model="small",
        )

        mock_repair.side_effect = [
            schema_failure(),
            schema_failure(),
            model_result(
                make_workflow(
                    with_analysis=True
                ),
                model="large",
            ),
        ]

        profile = AgentProfile(
            primary_model="small",
            fallback_model="large",
            primary_timeout_seconds=10,
            fallback_timeout_seconds=20,
            max_repairs=2,
        )

        result = run_preexecution_loop(
            REQUEST,
            client=object(),
            profile=profile,
        )

        self.assertEqual(
            result.status,
            PreExecutionStatus.READY_FOR_APPROVAL,
        )
        self.assertEqual(
            result.repair_attempts,
            2,
        )
        self.assertTrue(
            result.fallback_used
        )
        self.assertEqual(
            result.llm_call_count,
            4,
        )
        self.assertEqual(
            result.model_calls[-1].role,
            "fallback_repair",
        )

        fallback_feedback = (
            mock_repair.call_args_list[
                2
            ].kwargs[
                "validation_report"
            ]
        )

        failure_feedback_count = sum(
            issue.code
            == "previous_repair_output_invalid"
            for issue
            in fallback_feedback.issues
        )

        self.assertEqual(
            failure_feedback_count,
            2,
        )


if __name__ == "__main__":
    unittest.main()
