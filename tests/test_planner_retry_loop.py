"""Tests for initial planner retries and accounting."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hep_agent.models import (
    AgentProfile,
    ModelFailureType,
    ModelResponse,
    OllamaClientError,
)
from hep_agent.orchestration.preexecution import (
    FailureCategory,
    PreExecutionStatus,
    run_preexecution_loop,
)
from hep_agent.schemas import WorkflowIntent


REQUEST = (
    "Simulate proton-proton collisions producing "
    "an electron and a positron at 14 TeV. "
    "Generate 120 events. Do not use Pythia8 "
    "or Delphes."
)


def make_workflow() -> WorkflowIntent:
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
                    {"particle": "p"},
                    {"particle": "p"},
                ],
                "energy": {
                    "value_gev": 14000.0,
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
                        {"particle": "e+"},
                        {"particle": "e-"},
                    ],
                }
            ],
            "run": {
                "nevents": 120,
                "random_seed": 42,
                "timeout_seconds": 1800,
                "output_name": "planner_retry_test",
            },
            "pipeline": {
                "madgraph": True,
                "pythia8": False,
                "delphes": False,
                "madanalysis": False,
            },
            "analysis": None,
        }
    )


def planner_result():
    return SimpleNamespace(
        workflow=make_workflow(),
        model_response=ModelResponse(
            model="small",
            content="{}",
            total_duration_ns=(
                1_000_000_000
            ),
        ),
    )


def profile() -> AgentProfile:
    return AgentProfile(
        primary_model="small",
        fallback_model=None,
        primary_timeout_seconds=10,
        fallback_timeout_seconds=None,
        max_repairs=0,
        max_planner_attempts=2,
    )


class PlannerRetryLoopTests(
    unittest.TestCase
):
    @patch(
        "hep_agent.orchestration."
        "preexecution.plan_workflow"
    )
    def test_timeout_then_success_is_recorded(
        self,
        mock_plan,
    ) -> None:
        mock_plan.side_effect = [
            OllamaClientError(
                "temporary timeout",
                failure_type=(
                    ModelFailureType.TIMEOUT
                ),
            ),
            planner_result(),
        ]

        events = []

        result = run_preexecution_loop(
            REQUEST,
            client=object(),
            profile=profile(),
            progress_observer=events.append,
        )

        self.assertEqual(
            result.status,
            PreExecutionStatus.READY_FOR_APPROVAL,
        )
        self.assertEqual(
            result.llm_call_count,
            2,
        )
        self.assertEqual(
            [
                call.role
                for call in result.model_calls
            ],
            [
                (
                    "planner_"
                    "infrastructure_failure"
                ),
                "planner_retry_2",
            ],
        )


        self.assertEqual(
            [
                event.event_type
                for event in events
            ],
            [
                "model_call_started",
                "model_call_failed",
                "model_call_started",
                "model_call_completed",
                "validation_passed",
            ],
        )

    @patch(
        "hep_agent.orchestration."
        "preexecution.plan_workflow"
    )
    def test_two_timeouts_fail_safely(
        self,
        mock_plan,
    ) -> None:
        mock_plan.side_effect = [
            OllamaClientError(
                "timeout one",
                failure_type=(
                    ModelFailureType.TIMEOUT
                ),
            ),
            OllamaClientError(
                "timeout two",
                failure_type=(
                    ModelFailureType.TIMEOUT
                ),
            ),
        ]

        result = run_preexecution_loop(
            REQUEST,
            client=object(),
            profile=profile(),
        )

        self.assertEqual(
            result.status,
            PreExecutionStatus.FAILED,
        )
        self.assertEqual(
            result.failure_category,
            FailureCategory.MODEL_INFRASTRUCTURE,
        )
        self.assertEqual(
            result.llm_call_count,
            2,
        )
        self.assertEqual(
            [
                call.role
                for call in result.model_calls
            ],
            [
                (
                    "planner_"
                    "infrastructure_failure"
                ),
                (
                    "planner_retry_2_"
                    "infrastructure_failure"
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
