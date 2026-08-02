"""Tests for inclusive-process reconciliation."""

import unittest

from hep_agent.orchestration.process_reconciliation import (
    remove_redundant_inclusive_subprocesses,
)

from test_energy_scan import make_workflow


class ProcessReconciliationTests(
    unittest.TestCase
):
    def test_partonic_process_is_removed_when_inclusive_exists(
        self,
    ) -> None:
        workflow = make_workflow()

        inclusive = workflow.processes[0]

        partonic = inclusive.model_copy(
            update={
                "process_id": "partonic",
                "incoming_particles": [
                    "d",
                    "d~",
                ],
            },
            deep=True,
        )

        workflow = workflow.model_copy(
            update={
                "processes": [
                    inclusive,
                    partonic,
                ]
            },
            deep=True,
        )

        result = (
            remove_redundant_inclusive_subprocesses(
                workflow
            )
        )

        self.assertTrue(result.changed)
        self.assertEqual(
            result.removed_process_ids,
            ("partonic",),
        )
        self.assertEqual(
            len(result.workflow.processes),
            1,
        )
        self.assertEqual(
            result.workflow
            .processes[0]
            .incoming_particles,
            ["p", "p"],
        )

    def test_several_covered_subprocesses_are_removed(
        self,
    ) -> None:
        workflow = make_workflow()
        inclusive = workflow.processes[0]

        subprocesses = [
            inclusive.model_copy(
                update={
                    "process_id": process_id,
                    "incoming_particles": incoming,
                },
                deep=True,
            )
            for process_id, incoming in [
                (
                    "down",
                    ["d", "d~"],
                ),
                (
                    "up_down",
                    ["u", "d~"],
                ),
                (
                    "down_up",
                    ["d", "u~"],
                ),
            ]
        ]

        workflow = workflow.model_copy(
            update={
                "processes": [
                    inclusive,
                    *subprocesses,
                ]
            },
            deep=True,
        )

        result = (
            remove_redundant_inclusive_subprocesses(
                workflow
            )
        )

        self.assertEqual(
            result.removed_process_ids,
            (
                "down",
                "up_down",
                "down_up",
            ),
        )
        self.assertEqual(
            len(result.workflow.processes),
            1,
        )

    def test_partonic_only_workflow_is_preserved(
        self,
    ) -> None:
        workflow = make_workflow()

        partonic = (
            workflow.processes[0]
            .model_copy(
                update={
                    "incoming_particles": [
                        "d",
                        "d~",
                    ]
                },
                deep=True,
            )
        )

        workflow = workflow.model_copy(
            update={
                "processes": [
                    partonic
                ]
            },
            deep=True,
        )

        result = (
            remove_redundant_inclusive_subprocesses(
                workflow
            )
        )

        self.assertFalse(result.changed)
        self.assertEqual(
            result.workflow,
            workflow,
        )

    def test_distinct_final_state_is_preserved(
        self,
    ) -> None:
        workflow = make_workflow()
        inclusive = workflow.processes[0]

        distinct = inclusive.model_copy(
            update={
                "process_id": "muons",
                "incoming_particles": [
                    "d",
                    "d~",
                ],
                "final_particles": [
                    particle.model_copy(
                        update={
                            "particle": (
                                "mu+"
                                if index == 0
                                else "mu-"
                            )
                        }
                    )
                    for index, particle
                    in enumerate(
                        inclusive.final_particles
                    )
                ],
            },
            deep=True,
        )

        workflow = workflow.model_copy(
            update={
                "processes": [
                    inclusive,
                    distinct,
                ]
            },
            deep=True,
        )

        result = (
            remove_redundant_inclusive_subprocesses(
                workflow
            )
        )

        self.assertFalse(result.changed)
        self.assertEqual(
            len(result.workflow.processes),
            2,
        )


if __name__ == "__main__":
    unittest.main()
