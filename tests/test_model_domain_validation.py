"""Tests for model-relative particle-domain validation."""

from __future__ import annotations

import unittest

from hep_agent.schemas import (
    BeamSpec,
    ColliderSpec,
    ColliderType,
    EnergyMeaning,
    EnergySpec,
    ModelSource,
    ParticleNode,
    PhysicsModelSpec,
    ProcessSpec,
    TaskType,
    WorkflowIntent,
)
from hep_agent.validation import validate_workflow
from hep_agent.validation.model_domain import (
    model_domain_repair_matches,
    namespace_for_model,
    validate_model_domain,
)


def make_workflow(
    *,
    incoming=("p", "p"),
    final_particles=None,
    required_intermediates=(),
    excluded_particles=(),
    model_name="sm",
    model_source=ModelSource.BUILTIN,
    model_path=None,
) -> WorkflowIntent:
    """Build a minimal but valid workflow for domain testing."""

    if final_particles is None:
        final_particles = [ParticleNode(particle="t"), ParticleNode(particle="t~")]

    return WorkflowIntent(
        task_type=TaskType.RUN_SIMULATION,
        model=PhysicsModelSpec(
            name=model_name,
            source=model_source,
            model_path=model_path,
        ),
        collider=ColliderSpec(
            collider_type=ColliderType.HADRON,
            beams=[BeamSpec(particle="p"), BeamSpec(particle="p")],
            energy=EnergySpec(
                value_gev=13000.0,
                meaning=EnergyMeaning.TOTAL_CENTER_OF_MASS,
            ),
        ),
        processes=[
            ProcessSpec(
                incoming_particles=list(incoming),
                final_particles=list(final_particles),
                required_intermediates=list(required_intermediates),
                excluded_particles=list(excluded_particles),
            )
        ],
    )


class ModelDomainValidationTests(unittest.TestCase):
    def test_correct_top_pair_is_accepted(self) -> None:
        workflow = make_workflow(
            final_particles=[
                ParticleNode(particle="t"),
                ParticleNode(particle="t~"),
            ]
        )

        report = validate_model_domain(workflow)

        self.assertTrue(report.is_valid)

    def test_glued_token_is_rejected_with_split_suggestion(self) -> None:
        workflow = make_workflow(
            final_particles=[ParticleNode(particle="tt~")]
        )

        report = validate_model_domain(workflow)

        self.assertFalse(report.is_valid)

        codes = {issue.code for issue in report.errors}
        self.assertIn("unknown_model_particle", codes)

        message = report.errors[0].message
        self.assertIn("t", message)
        self.assertIn("t~", message)

    def test_only_exact_suggested_split_is_a_proven_repair(self) -> None:
        workflow = make_workflow(
            final_particles=[
                ParticleNode(particle="t~"),
                ParticleNode(particle="t"),
            ]
        )

        self.assertTrue(
            model_domain_repair_matches(
                workflow,
                requested_tokens=("tt~",),
                actual_tokens=("t~", "t"),
            )
        )
        self.assertFalse(
            model_domain_repair_matches(
                workflow,
                requested_tokens=("tt~",),
                actual_tokens=("h",),
            )
        )
        self.assertFalse(
            model_domain_repair_matches(
                workflow,
                requested_tokens=("t", "t~"),
                actual_tokens=("h",),
            )
        )

    def test_multiparticles_and_leptons_are_accepted(self) -> None:
        workflow = make_workflow(
            incoming=("p", "p"),
            final_particles=[
                ParticleNode(particle="e+"),
                ParticleNode(particle="e-"),
                ParticleNode(particle="j"),
            ],
        )

        report = validate_model_domain(workflow)

        self.assertTrue(report.is_valid)

    def test_partonic_q_qbar_is_accepted(self) -> None:
        # Guards existing behaviour: the codebase treats q / q~ as valid
        # partonic labels.
        workflow = make_workflow(
            incoming=("q", "q~"),
            final_particles=[
                ParticleNode(particle="mu+"),
                ParticleNode(particle="mu-"),
            ],
        )

        report = validate_model_domain(workflow)

        self.assertTrue(report.is_valid)

    def test_self_conjugate_and_charged_bosons_are_accepted(self) -> None:
        workflow = make_workflow(
            final_particles=[
                ParticleNode(particle="z"),
                ParticleNode(particle="a"),
                ParticleNode(particle="w+"),
                ParticleNode(particle="w-"),
                ParticleNode(particle="h"),
            ]
        )

        report = validate_model_domain(workflow)

        self.assertTrue(report.is_valid)

    def test_unknown_token_is_rejected(self) -> None:
        workflow = make_workflow(
            final_particles=[ParticleNode(particle="zprime")]
        )

        report = validate_model_domain(workflow)

        self.assertFalse(report.is_valid)
        self.assertEqual(
            report.errors[0].code, "unknown_model_particle"
        )

    def test_invalid_decay_daughter_is_flagged(self) -> None:
        # t -> (nonexistent daughter) must be caught by tree traversal.
        workflow = make_workflow(
            final_particles=[
                ParticleNode(
                    particle="t",
                    decay_products=[ParticleNode(particle="qq~")],
                ),
                ParticleNode(particle="t~"),
            ]
        )

        report = validate_model_domain(workflow)

        self.assertFalse(report.is_valid)
        codes = {issue.code for issue in report.errors}
        self.assertIn("unknown_model_particle", codes)

    def test_user_ufo_model_is_permissive(self) -> None:
        # We cannot know a user UFO namespace, so we must not reject.
        workflow = make_workflow(
            final_particles=[ParticleNode(particle="xyz1")],
            model_name="MyBSM",
            model_source=ModelSource.USER_UFO,
            model_path="/models/MyBSM",
        )

        namespace = namespace_for_model(workflow)
        self.assertFalse(namespace.authoritative)

        report = validate_model_domain(workflow)
        self.assertTrue(report.is_valid)

    def test_validate_workflow_blocks_glued_token(self) -> None:
        # Integration: the wiring into validate_workflow makes the invalid
        # token an error, so it can never reach approval or MadGraph.
        workflow = make_workflow(
            final_particles=[ParticleNode(particle="tt~")]
        )

        report = validate_workflow(workflow)

        self.assertFalse(report.is_valid)
        codes = {issue.code for issue in report.errors}
        self.assertIn("unknown_model_particle", codes)

    def test_validate_workflow_accepts_valid_top_pair(self) -> None:
        workflow = make_workflow(
            final_particles=[
                ParticleNode(particle="t"),
                ParticleNode(particle="t~"),
            ]
        )

        report = validate_workflow(workflow)

        self.assertTrue(report.is_valid)


if __name__ == "__main__":
    unittest.main()
