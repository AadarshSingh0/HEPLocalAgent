"""Tests for deterministic MadGraph process construction."""

import unittest

from hep_agent.builders import (
    MadGraphBuildError,
    build_madgraph_artifact,
)
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
    ProcessSpec,
    TaskType,
    WorkflowIntent,
)


def collider() -> ColliderSpec:
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


def workflow_with_processes(
    processes: list[ProcessSpec],
) -> WorkflowIntent:
    return WorkflowIntent(
        task_type=TaskType.GENERATE_PROCESS,
        model=PhysicsModelSpec(name="sm"),
        collider=collider(),
        processes=processes,
    )


class MadGraphBuilderTests(unittest.TestCase):
    def test_simple_dilepton_process(self) -> None:
        workflow = workflow_with_processes(
            [
                ProcessSpec(
                    incoming_particles=["p", "p"],
                    final_particles=[
                        ParticleNode(particle="e-"),
                        ParticleNode(particle="e+"),
                    ],
                )
            ]
        )

        artifact = build_madgraph_artifact(workflow)

        self.assertEqual(
            artifact.commands,
            (
                "import model sm",
                "generate p p > e- e+",
                "output hep_agent_output",
            ),
        )

    def test_nested_top_decay_chain(self) -> None:
        workflow = workflow_with_processes(
            [
                ProcessSpec(
                    incoming_particles=["p", "p"],
                    final_particles=[
                        ParticleNode(
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
                        ),
                        ParticleNode(
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
                        ),
                    ],
                )
            ]
        )

        artifact = build_madgraph_artifact(workflow)

        self.assertEqual(
            artifact.commands[1],
            "generate p p > t t~, "
            "(t > w+ b, w+ > mu+ vm), "
            "(t~ > w- b~, w- > j j)",
        )

    def test_intermediate_coupling_and_exclusion(self) -> None:
        workflow = workflow_with_processes(
            [
                ProcessSpec(
                    incoming_particles=["p", "p"],
                    final_particles=[
                        ParticleNode(particle="mu-"),
                        ParticleNode(particle="mu+"),
                    ],
                    required_intermediates=["z"],
                    excluded_particles=["a"],
                    coupling_orders={
                        "qed": CouplingOrderSpec(
                            value=2,
                            comparison=CouplingComparison.MAXIMUM,
                        )
                    },
                )
            ]
        )

        artifact = build_madgraph_artifact(workflow)

        self.assertEqual(
            artifact.commands[1],
            "generate p p > z > mu- mu+ QED<=2 / a",
        )

    def test_exact_amplitude_coupling_is_rejected(self) -> None:
        workflow = workflow_with_processes(
            [
                ProcessSpec(
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
            ]
        )

        with self.assertRaisesRegex(
            MadGraphBuildError,
            "single '=' as a maximum",
        ):
            build_madgraph_artifact(workflow)

    def test_multiple_processes_use_add_process(self) -> None:
        workflow = workflow_with_processes(
            [
                ProcessSpec(
                    process_id="electron_channel",
                    incoming_particles=["p", "p"],
                    final_particles=[
                        ParticleNode(particle="e-"),
                        ParticleNode(particle="e+"),
                    ],
                ),
                ProcessSpec(
                    process_id="muon_channel",
                    incoming_particles=["p", "p"],
                    final_particles=[
                        ParticleNode(particle="mu-"),
                        ParticleNode(particle="mu+"),
                    ],
                ),
            ]
        )

        artifact = build_madgraph_artifact(workflow)

        self.assertEqual(
            artifact.commands[1],
            "generate p p > e- e+",
        )
        self.assertEqual(
            artifact.commands[2],
            "add process p p > mu- mu+",
        )

    def test_conflicting_identical_particle_decays_are_rejected(
        self,
    ) -> None:
        workflow = workflow_with_processes(
            [
                ProcessSpec(
                    incoming_particles=["p", "p"],
                    final_particles=[
                        ParticleNode(
                            particle="z",
                            branch_id="z1",
                            decay_products=[
                                ParticleNode(particle="e-"),
                                ParticleNode(particle="e+"),
                            ],
                        ),
                        ParticleNode(
                            particle="z",
                            branch_id="z2",
                            decay_products=[
                                ParticleNode(particle="mu-"),
                                ParticleNode(particle="mu+"),
                            ],
                        ),
                    ],
                )
            ]
        )

        with self.assertRaises(MadGraphBuildError):
            build_madgraph_artifact(workflow)


if __name__ == "__main__":
    unittest.main()
