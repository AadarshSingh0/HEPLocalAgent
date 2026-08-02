"""Tests for inclusive process grounding."""

import unittest

from hep_agent.orchestration.grounding_repair import (
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
from hep_agent.validation import (
    extract_explicit_request_facts,
)


def make_bad_dilepton_workflow() -> WorkflowIntent:
    return WorkflowIntent(
        task_type=TaskType.RUN_SIMULATION,
        model=PhysicsModelSpec(
            name="sm"
        ),
        collider=ColliderSpec(
            collider_type=ColliderType.HADRON,
            beams=[
                BeamSpec(particle="p"),
                BeamSpec(particle="p"),
            ],
            energy=EnergySpec(
                value_gev=13_000,
                meaning=(
                    EnergyMeaning
                    .TOTAL_CENTER_OF_MASS
                ),
            ),
        ),
        processes=[
            ProcessSpec(
                incoming_particles=[
                    "q",
                    "q~",
                ],
                final_particles=[
                    ParticleNode(
                        particle="e+"
                    ),
                    ParticleNode(
                        particle="e-"
                    ),
                ],
                required_intermediates=[
                    "gamma",
                    "Z",
                ],
            )
        ],
        run=RunSettings(
            nevents=100
        ),
        pipeline=PipelineSpec(
            madgraph=True,
            pythia8=True,
            delphes=False,
        ),
    )


class ProcessConstraintGroundingTests(
    unittest.TestCase
):
    def test_symbolic_process_facts_are_extracted(
        self,
    ) -> None:
        facts = extract_explicit_request_facts(
            "Simulate p p > e+ e- at "
            "13 TeV with 100 events."
        )

        self.assertEqual(
            facts.collider_beams,
            ("p", "p"),
        )
        self.assertEqual(
            facts.process_incoming,
            ("p", "p"),
        )
        self.assertEqual(
            facts.final_particles,
            ("e+", "e-"),
        )

    def test_unrequested_intermediates_are_removed(
        self,
    ) -> None:
        result = apply_safe_grounding_corrections(
            (
                "Simulate p p > e+ e- at "
                "13 TeV with 100 events "
                "and Pythia8."
            ),
            make_bad_dilepton_workflow(),
        )

        process = result.workflow.processes[0]

        self.assertEqual(
            process.incoming_particles,
            ["p", "p"],
        )
        self.assertEqual(
            process.required_intermediates,
            [],
        )

        paths = {
            correction.path
            for correction
            in result.corrections
        }

        self.assertIn(
            (
                "processes[0]."
                "incoming_particles"
            ),
            paths,
        )
        self.assertIn(
            (
                "processes[0]."
                "required_intermediates"
            ),
            paths,
        )

    def test_explicit_intermediate_is_preserved(
        self,
    ) -> None:
        workflow = (
            make_bad_dilepton_workflow()
        )

        workflow.processes[
            0
        ].required_intermediates = [
            "z"
        ]

        result = apply_safe_grounding_corrections(
            (
                "Simulate p p > z > e+ e- "
                "at 13 TeV with 100 events."
            ),
            workflow,
        )

        self.assertEqual(
            result.workflow
            .processes[0]
            .required_intermediates,
            ["z"],
        )


if __name__ == "__main__":
    unittest.main()
