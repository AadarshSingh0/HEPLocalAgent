"""Tests for deterministic collider-energy scan planning."""

import unittest

from hep_agent.scans import (
    MAX_SCAN_POINTS,
    EnergyScanPlanError,
    build_energy_scan_plan,
    expand_energy_scan,
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


def make_workflow(
    *,
    nevents: int = 100,
    seed: int = 0,
) -> WorkflowIntent:
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
                    EnergyMeaning
                    .TOTAL_CENTER_OF_MASS
                ),
            ),
        ),
        processes=[
            ProcessSpec(
                process_id="dilepton",
                incoming_particles=["p", "p"],
                final_particles=[
                    ParticleNode(
                        particle="e+"
                    ),
                    ParticleNode(
                        particle="e-"
                    ),
                ],
            )
        ],
        run=RunSettings(
            nevents=nevents,
            random_seed=seed,
            output_name="dilepton",
        ),
        pipeline=PipelineSpec(
            madgraph=True,
            pythia8=False,
            delphes=False,
            madanalysis=False,
        ),
    )


class EnergyScanTests(unittest.TestCase):
    def test_energy_points_are_sorted(
        self,
    ) -> None:
        plan = build_energy_scan_plan(
            make_workflow(),
            energy_points_gev=[
                14_000,
                7_000,
                13_000,
            ],
        )

        self.assertEqual(
            plan.energy_points_gev,
            [
                7_000,
                13_000,
                14_000,
            ],
        )

    def test_duplicate_energies_are_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            EnergyScanPlanError
        ):
            build_energy_scan_plan(
                make_workflow(),
                energy_points_gev=[
                    13_000,
                    13_000,
                ],
            )

    def test_single_point_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            EnergyScanPlanError
        ):
            build_energy_scan_plan(
                make_workflow(),
                energy_points_gev=[
                    13_000
                ],
            )

    def test_nonpositive_energy_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            EnergyScanPlanError
        ):
            build_energy_scan_plan(
                make_workflow(),
                energy_points_gev=[
                    0,
                    13_000,
                ],
            )

    def test_too_many_points_are_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            EnergyScanPlanError
        ):
            build_energy_scan_plan(
                make_workflow(),
                energy_points_gev=[
                    float(index + 1)
                    for index in range(
                        MAX_SCAN_POINTS + 1
                    )
                ],
            )

    def test_total_event_limit_is_enforced(
        self,
    ) -> None:
        with self.assertRaises(
            EnergyScanPlanError
        ):
            build_energy_scan_plan(
                make_workflow(
                    nevents=100_001
                ),
                energy_points_gev=[
                    7_000,
                    13_000,
                ],
            )

    def test_expansion_has_unique_outputs_and_seeds(
        self,
    ) -> None:
        plan = build_energy_scan_plan(
            make_workflow(),
            energy_points_gev=[
                7_000,
                8_000,
                13_000,
                14_000,
            ],
        )

        expanded = expand_energy_scan(plan)

        self.assertEqual(
            expanded.point_count,
            4,
        )

        self.assertEqual(
            {
                point.random_seed
                for point in expanded.points
            },
            {
                1001,
                1002,
                1003,
                1004,
            },
        )

        self.assertEqual(
            len(
                {
                    point.output_name
                    for point in expanded.points
                }
            ),
            4,
        )

    def test_expansion_changes_each_energy(
        self,
    ) -> None:
        plan = build_energy_scan_plan(
            make_workflow(),
            energy_points_gev=[
                7_000,
                13_000,
            ],
        )

        expanded = expand_energy_scan(plan)

        self.assertEqual(
            [
                point.workflow
                .collider
                .energy
                .value_gev
                for point in expanded.points
            ],
            [
                7_000,
                13_000,
            ],
        )

    def test_base_workflow_is_not_modified(
        self,
    ) -> None:
        workflow = make_workflow()

        plan = build_energy_scan_plan(
            workflow,
            energy_points_gev=[
                7_000,
                14_000,
            ],
        )

        expand_energy_scan(plan)

        self.assertEqual(
            workflow
            .collider
            .energy
            .value_gev,
            13_000,
        )
        self.assertEqual(
            workflow.run.random_seed,
            0,
        )
        self.assertEqual(
            workflow.run.output_name,
            "dilepton",
        )


if __name__ == "__main__":
    unittest.main()
