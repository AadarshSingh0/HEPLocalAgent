"""Tests that MA5 runs separately from the MG5 launch interface."""

import unittest

from hep_agent.builders import (
    build_madgraph_workflow_artifact,
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
    validate_madgraph_workflow_artifact,
)


def make_workflow() -> WorkflowIntent:
    return WorkflowIntent(
        task_type=TaskType.RUN_SIMULATION,
        model=PhysicsModelSpec(
            name="sm",
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
                    EnergyMeaning.TOTAL_CENTER_OF_MASS
                ),
            ),
        ),
        processes=[
            ProcessSpec(
                process_id="dilepton",
                incoming_particles=["p", "p"],
                final_particles=[
                    ParticleNode(particle="e+"),
                    ParticleNode(particle="e-"),
                ],
            )
        ],
        run=RunSettings(
            nevents=100,
            output_name="dilepton",
        ),
        pipeline=PipelineSpec(
            madgraph=True,
            pythia8=True,
            delphes=False,
            madanalysis=True,
        ),
    )


class MadAnalysisPipelineSeparationTests(
    unittest.TestCase
):
    def test_ma5_request_does_not_enter_mg5_analysis(
        self,
    ) -> None:
        workflow = make_workflow()

        artifact = build_madgraph_workflow_artifact(
            workflow
        )

        self.assertIn(
            "shower=Pythia8",
            artifact.commands,
        )
        self.assertIn(
            "analysis=OFF",
            artifact.commands,
        )

        self.assertFalse(
            any(
                "MadAnalysis" in command
                for command in artifact.commands
            )
        )

    def test_mg5_artifact_remains_valid_when_ma5_requested(
        self,
    ) -> None:
        workflow = make_workflow()

        artifact = build_madgraph_workflow_artifact(
            workflow
        )

        report = validate_madgraph_workflow_artifact(
            workflow,
            artifact,
        )

        self.assertTrue(
            report.is_valid,
            msg=[
                (
                    issue.code,
                    issue.message,
                )
                for issue in report.issues
            ],
        )


if __name__ == "__main__":
    unittest.main()
