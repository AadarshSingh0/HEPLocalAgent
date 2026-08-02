"""Tests for the general collider-workflow schema."""

import unittest

from pydantic import ValidationError

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


def proton_collider() -> ColliderSpec:
    return ColliderSpec(
        collider_type=ColliderType.HADRON,
        beams=[
            BeamSpec(particle="p"),
            BeamSpec(particle="p"),
        ],
        energy=EnergySpec(
            value_gev=13_000,
            meaning=EnergyMeaning.TOTAL_CENTER_OF_MASS,
        ),
    )


class WorkflowSchemaTests(unittest.TestCase):
    def test_simple_dilepton_process(self) -> None:
        workflow = WorkflowIntent(
            task_type=TaskType.RUN_SIMULATION,
            model=PhysicsModelSpec(name="sm"),
            collider=proton_collider(),
            processes=[
                ProcessSpec(
                    incoming_particles=["p", "p"],
                    final_particles=[
                        ParticleNode(particle="e-"),
                        ParticleNode(particle="e+"),
                    ],
                )
            ],
        )

        self.assertEqual(workflow.model.name, "sm")
        self.assertEqual(workflow.run.nevents, 10_000)

    def test_partonic_process_inside_proton_collider(self) -> None:
        workflow = WorkflowIntent(
            task_type=TaskType.GENERATE_PROCESS,
            model=PhysicsModelSpec(name="sm"),
            collider=proton_collider(),
            processes=[
                ProcessSpec(
                    incoming_particles=["q", "q~"],
                    final_particles=[
                        ParticleNode(particle="mu-"),
                        ParticleNode(particle="mu+"),
                    ],
                )
            ],
        )

        self.assertEqual(workflow.collider.beams[0].particle, "p")
        self.assertEqual(
            workflow.processes[0].incoming_particles,
            ["q", "q~"],
        )

    def test_asymmetric_lepton_beams(self) -> None:
        workflow = WorkflowIntent(
            task_type=TaskType.RUN_SIMULATION,
            model=PhysicsModelSpec(name="sm"),
            collider=ColliderSpec(
                collider_type=ColliderType.LEPTON,
                beams=[
                    BeamSpec(particle="e-"),
                    BeamSpec(particle="e+"),
                ],
                energy=EnergySpec(
                    value_gev=250,
                    meaning=EnergyMeaning.TOTAL_CENTER_OF_MASS,
                ),
            ),
            processes=[
                ProcessSpec(
                    incoming_particles=["e-", "e+"],
                    final_particles=[
                        ParticleNode(particle="z"),
                        ParticleNode(particle="h"),
                    ],
                )
            ],
        )

        self.assertEqual(workflow.collider.energy.value_gev, 250)

    def test_nested_top_decay_tree(self) -> None:
        top = ParticleNode(
            particle="t",
            branch_id="top1",
            decay_products=[
                ParticleNode(
                    particle="w+",
                    branch_id="wplus1",
                    decay_products=[
                        ParticleNode(particle="mu+"),
                        ParticleNode(particle="vm"),
                    ],
                ),
                ParticleNode(particle="b"),
            ],
        )

        antitop = ParticleNode(
            particle="t~",
            branch_id="antitop1",
            decay_products=[
                ParticleNode(
                    particle="w-",
                    branch_id="wminus1",
                    decay_products=[
                        ParticleNode(particle="j"),
                        ParticleNode(particle="j"),
                    ],
                ),
                ParticleNode(particle="b~"),
            ],
        )

        workflow = WorkflowIntent(
            task_type=TaskType.RUN_SIMULATION,
            model=PhysicsModelSpec(name="sm"),
            collider=proton_collider(),
            processes=[
                ProcessSpec(
                    process_id="ttbar_semileptonic",
                    incoming_particles=["p", "p"],
                    final_particles=[top, antitop],
                )
            ],
            run=RunSettings(nevents=20_000),
            pipeline=PipelineSpec(
                madgraph=True,
                pythia8=True,
            ),
        )

        top_nodes = list(workflow.processes[0].final_particles[0].walk())

        self.assertEqual(workflow.run.nevents, 20_000)
        self.assertEqual(len(top_nodes), 5)
        self.assertTrue(workflow.pipeline.pythia8)

    def test_duplicate_branch_ids_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ProcessSpec(
                incoming_particles=["p", "p"],
                final_particles=[
                    ParticleNode(particle="z", branch_id="same_branch"),
                    ParticleNode(particle="z", branch_id="same_branch"),
                ],
            )


if __name__ == "__main__":
    unittest.main()
