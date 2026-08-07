"""Tests for model-aware domain validation of UFO/BSM models."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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
from hep_agent.validation.model_domain import (
    namespace_for_model,
    validate_model_domain,
)


# A minimal UFO-style particles.py. It is parsed with ast, never executed, so
# undefined names in the constructor arguments are irrelevant.
PARTICLES_PY = """
from object_library import all_particles, Particle

t = Particle(pdg_code=6, name='t', antiname='t~', spin=2, color=3)
e_minus = Particle(pdg_code=11, name='e-', antiname='e+', spin=2, color=1)
z = Particle(pdg_code=23, name='z', antiname='z', spin=3, color=1)
x1 = Particle(pdg_code=1000022, name='x1', antiname='x1', spin=2, color=1)
xd = Particle(pdg_code=1000001, name='xd', antiname='xd~', spin=1, color=3)
"""


def ufo_workflow(model_path, final_particles, *, incoming=("p", "p")):
    return WorkflowIntent(
        task_type=TaskType.RUN_SIMULATION,
        model=PhysicsModelSpec(
            name="MyBSM",
            source=ModelSource.USER_UFO,
            model_path=str(model_path),
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
            )
        ],
    )


class UfoDomainValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.model_dir = Path(self._dir.name)
        (self.model_dir / "particles.py").write_text(PARTICLES_PY)

    def tearDown(self) -> None:
        self._dir.cleanup()

    def test_namespace_is_authoritative_when_particles_parse(self) -> None:
        workflow = ufo_workflow(
            self.model_dir, [ParticleNode(particle="x1")]
        )
        namespace = namespace_for_model(workflow)
        self.assertTrue(namespace.authoritative)

    def test_bsm_particle_is_accepted(self) -> None:
        workflow = ufo_workflow(
            self.model_dir,
            [ParticleNode(particle="xd"), ParticleNode(particle="xd~")],
        )
        self.assertTrue(validate_model_domain(workflow).is_valid)

    def test_model_defined_sm_particles_are_accepted(self) -> None:
        workflow = ufo_workflow(
            self.model_dir,
            [ParticleNode(particle="e-"), ParticleNode(particle="e+")],
        )
        self.assertTrue(validate_model_domain(workflow).is_valid)

    def test_default_multiparticles_are_accepted(self) -> None:
        # p / j come from MadGraph defaults, not from particles.py.
        workflow = ufo_workflow(
            self.model_dir,
            [ParticleNode(particle="x1")],
            incoming=("p", "p"),
        )
        self.assertTrue(validate_model_domain(workflow).is_valid)

    def test_token_not_in_model_is_rejected(self) -> None:
        # 'susy' is not defined by this model -> caught before MadGraph.
        workflow = ufo_workflow(
            self.model_dir, [ParticleNode(particle="susy")]
        )
        report = validate_model_domain(workflow)
        self.assertFalse(report.is_valid)
        self.assertEqual(report.errors[0].code, "unknown_model_particle")

    def test_glued_token_still_rejected_for_bsm_model(self) -> None:
        workflow = ufo_workflow(
            self.model_dir, [ParticleNode(particle="x1x1")]
        )
        self.assertFalse(validate_model_domain(workflow).is_valid)

    def test_nonexistent_model_path_is_permissive(self) -> None:
        workflow = ufo_workflow(
            "/no/such/ufo/model", [ParticleNode(particle="anything")]
        )
        namespace = namespace_for_model(workflow)
        self.assertFalse(namespace.authoritative)
        self.assertTrue(validate_model_domain(workflow).is_valid)

    def test_unparseable_particles_file_is_permissive(self) -> None:
        with tempfile.TemporaryDirectory() as empty_dir:
            # particles.py with no Particle(...) constructors.
            (Path(empty_dir) / "particles.py").write_text(
                "# no particle definitions here\nX = 1\n"
            )
            workflow = ufo_workflow(
                empty_dir, [ParticleNode(particle="whatever")]
            )
            namespace = namespace_for_model(workflow)
            self.assertFalse(namespace.authoritative)
            self.assertTrue(validate_model_domain(workflow).is_valid)


if __name__ == "__main__":
    unittest.main()
