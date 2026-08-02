"""Tests for full deterministic MG5 launch workflows."""

import unittest

from hep_agent.builders import (
    MadGraphBuildError,
    MadGraphWorkflowArtifact,
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


def make_workflow(
    *,
    beams: tuple[str, str] = ("p", "p"),
    energy_gev: float = 13_000,
    energy_meaning: EnergyMeaning = (
        EnergyMeaning.TOTAL_CENTER_OF_MASS
    ),
    pythia8: bool = False,
    delphes: bool = False,
) -> WorkflowIntent:
    return WorkflowIntent(
        task_type=TaskType.RUN_SIMULATION,
        model=PhysicsModelSpec(name="sm"),
        collider=ColliderSpec(
            collider_type=ColliderType.HADRON,
            beams=[
                BeamSpec(particle=beams[0]),
                BeamSpec(particle=beams[1]),
            ],
            energy=EnergySpec(
                value_gev=energy_gev,
                meaning=energy_meaning,
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
        run=RunSettings(
            nevents=20_000,
            random_seed=12345,
            output_name="dilepton_run",
        ),
        pipeline=PipelineSpec(
            madgraph=True,
            pythia8=pythia8,
            delphes=delphes,
        ),
    )


class MadGraphWorkflowTests(unittest.TestCase):
    def test_total_energy_is_split_between_beams(self) -> None:
        workflow = make_workflow()

        artifact = build_madgraph_workflow_artifact(workflow)

        self.assertIn("set ebeam1 6500", artifact.commands)
        self.assertIn("set ebeam2 6500", artifact.commands)

    def test_per_beam_energy_is_preserved(self) -> None:
        workflow = make_workflow(
            energy_gev=7000,
            energy_meaning=EnergyMeaning.PER_BEAM,
        )

        artifact = build_madgraph_workflow_artifact(workflow)

        self.assertIn("set ebeam1 7000", artifact.commands)
        self.assertIn("set ebeam2 7000", artifact.commands)

    def test_pythia_and_delphes_are_enabled(self) -> None:
        workflow = make_workflow(
            pythia8=True,
            delphes=True,
        )

        artifact = build_madgraph_workflow_artifact(workflow)

        self.assertIn("shower=Pythia8", artifact.commands)
        self.assertIn("detector=Delphes", artifact.commands)

    def test_complete_artifact_is_valid(self) -> None:
        workflow = make_workflow(
            pythia8=True,
            delphes=True,
        )

        artifact = build_madgraph_workflow_artifact(workflow)
        report = validate_madgraph_workflow_artifact(
            workflow,
            artifact,
        )

        self.assertTrue(report.is_valid)

    def test_modified_artifact_is_rejected(self) -> None:
        workflow = make_workflow()
        valid = build_madgraph_workflow_artifact(workflow)

        modified = MadGraphWorkflowArtifact(
            process_artifact=valid.process_artifact,
            launch_commands=(
                "launch wrong_directory",
                *valid.launch_commands[1:],
            ),
        )

        report = validate_madgraph_workflow_artifact(
            workflow,
            modified,
        )

        self.assertFalse(report.is_valid)
        self.assertIn(
            "workflow_artifact_mismatch",
            [issue.code for issue in report.errors],
        )

    def test_unsupported_asymmetric_energy_is_rejected(self) -> None:
        workflow = make_workflow(
            beams=("e-", "p"),
        )

        with self.assertRaises(MadGraphBuildError):
            build_madgraph_workflow_artifact(workflow)


if __name__ == "__main__":
    unittest.main()
