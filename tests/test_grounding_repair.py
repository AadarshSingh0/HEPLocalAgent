"""Tests for safe deterministic grounding corrections."""

import unittest

from hep_agent.orchestration import (
    apply_safe_grounding_corrections,
)
from hep_agent.schemas import (
    BeamSpec,
    ColliderSpec,
    ColliderType,
    EnergyMeaning,
    EnergySpec,
    ParticleNode,
    PhysicsModelSpec,
    PipelineSpec,
    ProcessSpec,
    RunSettings,
    TaskType,
    WorkflowIntent,
)
from hep_agent.validation import validate_request_grounding


REQUEST = (
    "Simulate proton-proton collisions producing an electron and a "
    "positron at a total centre-of-mass energy of 13 TeV. "
    "Generate 10000 events. Do not use Pythia8 or Delphes."
)


def make_workflow(
    *,
    incoming: tuple[str, str] = ("q", "q~"),
    final: tuple[str, str] = ("e+", "e-"),
    nevents: int = 5000,
    pythia8: bool = True,
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
                incoming_particles=list(incoming),
                final_particles=[
                    ParticleNode(particle=final[0]),
                    ParticleNode(particle=final[1]),
                ],
            )
        ],
        run=RunSettings(nevents=nevents),
        pipeline=PipelineSpec(
            madgraph=True,
            pythia8=pythia8,
            delphes=False,
        ),
    )


class GroundingRepairTests(unittest.TestCase):
    def test_explicit_incoming_and_run_values_are_corrected(
        self,
    ) -> None:
        result = apply_safe_grounding_corrections(
            REQUEST,
            make_workflow(),
        )

        self.assertEqual(
            result.workflow.processes[0].incoming_particles,
            ["p", "p"],
        )
        self.assertEqual(result.workflow.run.nevents, 10_000)
        self.assertFalse(result.workflow.pipeline.pythia8)
        self.assertTrue(result.changed)

    def test_corrected_workflow_passes_grounding(self) -> None:
        correction = apply_safe_grounding_corrections(
            REQUEST,
            make_workflow(),
        )

        grounding = validate_request_grounding(
            REQUEST,
            correction.workflow,
        )

        self.assertTrue(grounding.report.is_valid)

    def test_stale_planner_notes_are_removed(self) -> None:
        workflow = make_workflow()
        workflow.notes = [
            "Process inferred as q q~ -> e+ e-."
        ]

        result = apply_safe_grounding_corrections(
            REQUEST,
            workflow,
        )

        self.assertEqual(
            result.workflow.notes,
            [
                "Deterministic grounding corrections were applied; "
                "see the correction audit trail."
            ],
        )


    def test_final_state_is_not_silently_corrected(self) -> None:
        correction = apply_safe_grounding_corrections(
            REQUEST,
            make_workflow(final=("mu+", "mu-")),
        )

        grounding = validate_request_grounding(
            REQUEST,
            correction.workflow,
        )

        self.assertFalse(grounding.report.is_valid)
        self.assertIn(
            "explicit_final_state_mismatch",
            [issue.code for issue in grounding.report.errors],
        )

    def test_proven_invalid_explicit_token_repair_survives_grounding(
        self,
    ) -> None:
        request = (
            "Using the Standard Model, simulate p p > tt~ at "
            "13 TeV with 100 events. Do not use Pythia8 or Delphes."
        )
        workflow = make_workflow(
            incoming=("p", "p"),
            final=("t~", "t"),
            nevents=100,
            pythia8=False,
        )

        result = apply_safe_grounding_corrections(
            request,
            workflow,
        )

        particles = tuple(
            node.particle
            for node in result.workflow.processes[0].final_particles
        )

        self.assertEqual(particles, ("t~", "t"))
        self.assertTrue(
            validate_request_grounding(
                request,
                result.workflow,
            ).report.is_valid
        )
        self.assertTrue(
            any(
                correction.requires_confirmation
                for correction in result.corrections
            )
        )

    def test_unrelated_particle_does_not_replace_invalid_explicit_token(
        self,
    ) -> None:
        request = (
            "Using the Standard Model, simulate p p > tt~ at "
            "13 TeV with 100 events. Do not use Pythia8 or Delphes."
        )
        workflow = make_workflow(
            incoming=("p", "p"),
            final=("h", "h"),
            nevents=100,
            pythia8=False,
        )

        result = apply_safe_grounding_corrections(
            request,
            workflow,
        )

        particles = tuple(
            node.particle
            for node in result.workflow.processes[0].final_particles
        )
        self.assertEqual(particles, ("tt~",))


if __name__ == "__main__":
    unittest.main()
