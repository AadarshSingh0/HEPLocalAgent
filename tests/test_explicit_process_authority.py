"""Explicit MadGraph-style syntax must be authoritative."""

import unittest

from hep_agent.orchestration.grounding_repair import (
    apply_safe_grounding_corrections,
)
from hep_agent.schemas import (
    WorkflowIntent,
)
from hep_agent.validation.grounding import (
    extract_explicit_request_facts,
)


def make_wrong_workflow(
    *,
    incoming: list[str],
    final_particles: list[dict],
    required_intermediates: list[str] | None = None,
) -> WorkflowIntent:
    return WorkflowIntent.model_validate(
        {
            "schema_version": "1.0",
            "task_type": "run_simulation",
            "model": {
                "name": "sm",
                "source": "builtin",
                "model_path": None,
            },
            "collider": {
                "collider_type": "hadron",
                "beams": [
                    {
                        "particle": "p",
                    },
                    {
                        "particle": "p",
                    },
                ],
                "energy": {
                    "value_gev": 13000.0,
                    "meaning": (
                        "total_center_of_mass"
                    ),
                },
            },
            "processes": [
                {
                    "process_id": "process_001",
                    "incoming_particles": incoming,
                    "final_particles": (
                        final_particles
                    ),
                    "required_intermediates": (
                        required_intermediates
                        or []
                    ),
                    "excluded_particles": [],
                    "coupling_orders": {},
                }
            ],
            "run": {
                "nevents": 100,
                "random_seed": None,
                "timeout_seconds": 1800,
                "output_name": None,
            },
            "pipeline": {
                "madgraph": True,
                "pythia8": False,
                "delphes": False,
                "madanalysis": False,
            },
            "analysis": None,
        }
    )


class ExplicitProcessAuthorityTests(
    unittest.TestCase
):
    def test_grounding_facts_preserve_extra_jet(
        self,
    ) -> None:
        facts = extract_explicit_request_facts(
            (
                "Simulate p p > e+ e- j at "
                "13 TeV with 100 events."
            )
        )

        self.assertEqual(
            facts.process_incoming,
            ("p", "p"),
        )

        self.assertEqual(
            facts.final_particles,
            ("e+", "e-", "j"),
        )

    def test_unrequested_top_decays_are_removed(
        self,
    ) -> None:
        workflow = make_wrong_workflow(
            incoming=[
                "p",
                "p",
            ],
            final_particles=[
                {
                    "particle": "t",
                    "decay_products": [
                        {
                            "particle": "b",
                        }
                    ],
                },
                {
                    "particle": "t~",
                    "decay_products": [
                        {
                            "particle": "b~",
                        }
                    ],
                },
            ],
        )

        result = apply_safe_grounding_corrections(
            (
                "Simulate p p > t t~ at "
                "13 TeV with 100 events."
            ),
            workflow,
        )

        process = result.workflow.processes[0]

        self.assertEqual(
            [
                node.particle
                for node in process.final_particles
            ],
            [
                "t",
                "t~",
            ],
        )

        self.assertTrue(
            all(
                not node.decay_products
                for node
                in process.final_particles
            )
        )

    def test_two_to_three_process_is_restored(
        self,
    ) -> None:
        workflow = make_wrong_workflow(
            incoming=[
                "p",
                "p",
            ],
            final_particles=[
                {
                    "particle": "t",
                    "decay_products": [
                        {
                            "particle": "b",
                        }
                    ],
                },
                {
                    "particle": "t~",
                    "decay_products": [
                        {
                            "particle": "b~",
                        }
                    ],
                },
                {
                    "particle": "g",
                },
            ],
        )

        result = apply_safe_grounding_corrections(
            (
                "Simulate p p > t t~ j at "
                "13 TeV with 100 events."
            ),
            workflow,
        )

        process = result.workflow.processes[0]

        self.assertEqual(
            [
                node.particle
                for node in process.final_particles
            ],
            [
                "t",
                "t~",
                "j",
            ],
        )

        self.assertTrue(
            all(
                not node.decay_products
                for node
                in process.final_particles
            )
        )

    def test_partonic_process_is_not_replaced_by_beams(
        self,
    ) -> None:
        workflow = make_wrong_workflow(
            incoming=[
                "p",
                "p",
            ],
            final_particles=[
                {
                    "particle": "u",
                },
                {
                    "particle": "u",
                },
            ],
        )

        result = apply_safe_grounding_corrections(
            (
                "At a 13 TeV proton-proton "
                "collider, simulate the hard "
                "process q q > u u with "
                "100 events."
            ),
            workflow,
        )

        self.assertEqual(
            result.workflow
            .processes[0]
            .incoming_particles,
            [
                "q",
                "q",
            ],
        )

        self.assertEqual(
            [
                node.particle
                for node
                in result.workflow
                .processes[0]
                .final_particles
            ],
            [
                "u",
                "u",
            ],
        )

    def test_explicit_channel_is_restored(
        self,
    ) -> None:
        workflow = make_wrong_workflow(
            incoming=[
                "p",
                "p",
            ],
            final_particles=[
                {
                    "particle": "e+",
                },
                {
                    "particle": "e-",
                },
            ],
            required_intermediates=[
                "a",
            ],
        )

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
            [
                "z",
            ],
        )


if __name__ == "__main__":
    unittest.main()


class ExplicitProcessEnergyClauseTests(
    unittest.TestCase
):
    def test_verbose_center_of_mass_energy_clause(
        self,
    ) -> None:
        from hep_agent.validation.process_request import (
            extract_explicit_process_expression,
        )

        result = (
            extract_explicit_process_expression(
                (
                    "Simulate e+ e- > mu+ mu- at "
                    "a total center-of-mass energy "
                    "of 250 GeV with 100 events."
                )
            )
        )

        self.assertIsNotNone(
            result
        )

        self.assertEqual(
            result.incoming_particles,
            (
                "e+",
                "e-",
            ),
        )

        self.assertEqual(
            result.final_particles,
            (
                "mu+",
                "mu-",
            ),
        )

        self.assertEqual(
            result.required_intermediates,
            (),
        )
