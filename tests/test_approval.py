"""Tests for the approval and five-second auto-confirm policy."""

import unittest

from hep_agent.orchestration import (
    ApprovalContext,
    ApprovalDecision,
    decide_approval,
)
from hep_agent.schemas import (
    BeamSpec,
    ColliderSpec,
    ColliderType,
    EnergyMeaning,
    EnergySpec,
    FieldSource,
    ParticleNode,
    PhysicsModelSpec,
    ProcessSpec,
    RunSettings,
    TaskType,
    WorkflowIntent,
)
from hep_agent.validation import validate_workflow


def make_workflow(
    *,
    nevents: int = 10_000,
    field_sources: dict[str, FieldSource] | None = None,
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
                incoming_particles=["p", "p"],
                final_particles=[
                    ParticleNode(particle="e-"),
                    ParticleNode(particle="e+"),
                ],
            )
        ],
        run=RunSettings(nevents=nevents),
        field_sources=field_sources or {},
    )


class ApprovalTests(unittest.TestCase):
    def test_safe_workflow_auto_confirms_after_five_seconds(self) -> None:
        workflow = make_workflow()
        report = validate_workflow(workflow)

        result = decide_approval(workflow, report)

        self.assertEqual(
            result.decision,
            ApprovalDecision.AUTO_CONFIRM,
        )
        self.assertEqual(result.auto_confirm_delay_seconds, 5)

    def test_validation_error_is_blocked(self) -> None:
        workflow = make_workflow()
        workflow.pipeline.madgraph = False
        report = validate_workflow(workflow)

        result = decide_approval(workflow, report)

        self.assertEqual(
            result.decision,
            ApprovalDecision.BLOCKED,
        )
        self.assertFalse(result.may_execute)

    def test_large_event_warning_requires_confirmation(self) -> None:
        workflow = make_workflow(nevents=200_000)
        report = validate_workflow(workflow)

        result = decide_approval(workflow, report)

        self.assertEqual(
            result.decision,
            ApprovalDecision.EXPLICIT_CONFIRMATION,
        )

    def test_physics_inference_requires_confirmation(self) -> None:
        workflow = make_workflow(
            field_sources={
                "collider.energy.value_gev":
                    FieldSource.MODEL_INFERENCE,
            }
        )
        report = validate_workflow(workflow)

        result = decide_approval(workflow, report)

        self.assertEqual(
            result.decision,
            ApprovalDecision.EXPLICIT_CONFIRMATION,
        )

    def test_physics_changing_repair_requires_confirmation(self) -> None:
        workflow = make_workflow()
        report = validate_workflow(workflow)

        result = decide_approval(
            workflow,
            report,
            context=ApprovalContext(
                repair_changed_physics=True,
            ),
        )

        self.assertEqual(
            result.decision,
            ApprovalDecision.EXPLICIT_CONFIRMATION,
        )


if __name__ == "__main__":
    unittest.main()
