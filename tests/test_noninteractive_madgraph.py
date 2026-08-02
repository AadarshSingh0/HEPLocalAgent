"""Tests for noninteractive MadGraph execution settings."""

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


def make_workflow() -> WorkflowIntent:
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
                process_id="dilepton",
                incoming_particles=["p", "p"],
                final_particles=[
                    ParticleNode(particle="e+"),
                    ParticleNode(particle="e-"),
                ],
            )
        ],
        run=RunSettings(
            nevents=10,
            output_name="test_output",
        ),
        pipeline=PipelineSpec(
            madgraph=True,
            pythia8=False,
            delphes=False,
            madanalysis=False,
        ),
    )


class NoninteractiveMadGraphTests(unittest.TestCase):
    def test_browser_opening_is_disabled_before_launch(
        self,
    ) -> None:
        artifact = build_madgraph_workflow_artifact(
            make_workflow()
        )

        commands = artifact.commands

        setting = (
            "set automatic_html_opening False --no_save"
        )
        launch = "launch test_output"

        self.assertIn(setting, commands)
        self.assertIn(launch, commands)
        self.assertLess(
            commands.index(setting),
            commands.index(launch),
        )


if __name__ == "__main__":
    unittest.main()
