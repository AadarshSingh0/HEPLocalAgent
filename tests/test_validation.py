"""Tests for deterministic workflow and artifact validation."""

import unittest

from hep_agent.builders import MadGraphArtifact, build_madgraph_artifact
from hep_agent.schemas import (
    BeamSpec,
    ColliderSpec,
    ColliderType,
    CouplingComparison,
    CouplingOrderSpec,
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
    validate_madgraph_artifact,
    validate_workflow,
)


def make_workflow(
    *,
    pipeline: PipelineSpec | None = None,
    run: RunSettings | None = None,
    process: ProcessSpec | None = None,
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
            process
            or ProcessSpec(
                incoming_particles=["p", "p"],
                final_particles=[
                    ParticleNode(particle="e-"),
                    ParticleNode(particle="e+"),
                ],
            )
        ],
        run=run or RunSettings(),
        pipeline=pipeline or PipelineSpec(),
    )


class ValidationTests(unittest.TestCase):
    def test_valid_workflow_and_artifact(self) -> None:
        workflow = make_workflow()
        workflow_report = validate_workflow(workflow)

        self.assertTrue(workflow_report.is_valid)
        self.assertEqual(workflow_report.errors, ())

        artifact = build_madgraph_artifact(workflow)
        artifact_report = validate_madgraph_artifact(
            workflow,
            artifact,
        )

        self.assertTrue(artifact_report.is_valid)

    def test_delphes_without_pythia_is_rejected(self) -> None:
        workflow = make_workflow(
            pipeline=PipelineSpec(
                madgraph=True,
                pythia8=False,
                delphes=True,
            )
        )

        report = validate_workflow(workflow)

        self.assertFalse(report.is_valid)
        self.assertIn(
            "delphes_requires_pythia",
            [issue.code for issue in report.errors],
        )

    def test_unsafe_output_name_is_rejected(self) -> None:
        workflow = make_workflow(
            run=RunSettings(output_name="../unsafe")
        )

        report = validate_workflow(workflow)

        self.assertFalse(report.is_valid)
        self.assertIn(
            "unsafe_output_name",
            [issue.code for issue in report.errors],
        )

    def test_large_event_count_produces_warning(self) -> None:
        workflow = make_workflow(
            run=RunSettings(nevents=200_000)
        )

        report = validate_workflow(workflow)

        self.assertTrue(report.is_valid)
        self.assertIn(
            "large_event_count",
            [issue.code for issue in report.warnings],
        )

    def test_unsupported_coupling_minimum_is_rejected(self) -> None:
        process = ProcessSpec(
            incoming_particles=["p", "p"],
            final_particles=[
                ParticleNode(particle="t"),
                ParticleNode(particle="t~"),
            ],
            coupling_orders={
                "QCD": CouplingOrderSpec(
                    value=2,
                    comparison=CouplingComparison.MINIMUM,
                )
            },
        )

        report = validate_workflow(
            make_workflow(process=process)
        )

        self.assertFalse(report.is_valid)
        self.assertIn(
            "unsupported_minimum_coupling",
            [issue.code for issue in report.errors],
        )

    def test_unsupported_amplitude_exact_coupling_is_rejected(
        self,
    ) -> None:
        process = ProcessSpec(
            incoming_particles=["p", "p"],
            final_particles=[
                ParticleNode(particle="e-"),
                ParticleNode(particle="e+"),
            ],
            coupling_orders={
                "QED": CouplingOrderSpec(
                    value=2,
                    comparison=CouplingComparison.EXACT,
                )
            },
        )

        report = validate_workflow(
            make_workflow(process=process)
        )

        self.assertFalse(report.is_valid)
        self.assertIn(
            "unsupported_exact_coupling",
            [issue.code for issue in report.errors],
        )

    def test_modified_artifact_is_rejected(self) -> None:
        workflow = make_workflow()
        artifact = MadGraphArtifact(
            commands=(
                "import model sm",
                "generate p p > mu- mu+",
                "output hep_agent_output",
            )
        )

        report = validate_madgraph_artifact(
            workflow,
            artifact,
        )

        self.assertFalse(report.is_valid)
        self.assertIn(
            "artifact_mismatch",
            [issue.code for issue in report.errors],
        )


if __name__ == "__main__":
    unittest.main()
