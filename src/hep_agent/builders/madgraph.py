"""Deterministic MadGraph process builder.

This module converts a validated WorkflowIntent into MadGraph commands.

It does not call an LLM and does not execute MadGraph.
"""

from __future__ import annotations

from dataclasses import dataclass

from hep_agent.schemas import (
    CouplingComparison,
    ParticleNode,
    ProcessSpec,
    WorkflowIntent,
)


class MadGraphBuildError(ValueError):
    """Raised when a workflow cannot be represented safely."""


@dataclass(frozen=True)
class MadGraphArtifact:
    """Deterministically generated MadGraph command artifact."""

    commands: tuple[str, ...]

    @property
    def text(self) -> str:
        """Return commands as a file-ready string."""

        return "\n".join(self.commands) + "\n"


def _render_model_import(workflow: WorkflowIntent) -> str:
    """Construct the MadGraph model-import command."""

    model = workflow.model

    if model.model_path:
        return f"import model {model.model_path}"

    return f"import model {model.name}"


def _render_coupling_orders(process: ProcessSpec) -> str:
    """Render structured coupling-order restrictions."""

    rendered: list[str] = []

    for name in sorted(process.coupling_orders):
        order = process.coupling_orders[name]
        coupling_name = name.upper()

        if order.comparison == CouplingComparison.EXACT:
            operator = "="
        elif order.comparison == CouplingComparison.MAXIMUM:
            operator = "<="
        else:
            raise MadGraphBuildError(
                "Minimum coupling-order restrictions are not yet "
                "supported safely."
            )

        rendered.append(f"{coupling_name}{operator}{order.value}")

    if not rendered:
        return ""

    return " " + " ".join(rendered)


def _render_decay_chain(node: ParticleNode) -> str:
    """Recursively render one MadGraph decay chain."""

    if not node.decay_products:
        raise MadGraphBuildError(
            f"Particle {node.particle!r} has no decay products."
        )

    daughters = " ".join(
        daughter.particle for daughter in node.decay_products
    )

    direct_decay = f"{node.particle} > {daughters}"

    nested_decays = [
        _render_decay_chain(daughter)
        for daughter in node.decay_products
        if daughter.decay_products
    ]

    if not nested_decays:
        return direct_decay

    return f"({direct_decay}, {', '.join(nested_decays)})"


def _decay_signature(node: ParticleNode) -> tuple:
    """Return a comparable representation of a decay tree."""

    return (
        node.particle,
        tuple(_decay_signature(child) for child in node.decay_products),
    )


def _check_identical_particle_decays(process: ProcessSpec) -> None:
    """Reject different decays assigned to identical final particles.

    MadGraph branch identifiers are not physical particle names.
    Therefore, two identical produced particles cannot safely be given
    different decay instructions through branch IDs alone.
    """

    signatures_by_particle: dict[str, set[tuple]] = {}

    for node in process.final_particles:
        if not node.decay_products:
            continue

        signatures_by_particle.setdefault(node.particle, set()).add(
            _decay_signature(node)
        )

    conflicting_particles = [
        particle
        for particle, signatures in signatures_by_particle.items()
        if len(signatures) > 1
    ]

    if conflicting_particles:
        particles = ", ".join(sorted(conflicting_particles))
        raise MadGraphBuildError(
            "Identical final-state particles have conflicting decay "
            f"trees: {particles}."
        )


def render_process_expression(process: ProcessSpec) -> str:
    """Render one process without generate/add-process prefix."""

    _check_identical_particle_decays(process)

    incoming = " ".join(process.incoming_particles)
    final = " ".join(
        particle.particle for particle in process.final_particles
    )

    if len(process.required_intermediates) > 1:
        raise MadGraphBuildError(
            "More than one required intermediate is not yet supported "
            "safely by schema version 1."
        )

    if process.required_intermediates:
        intermediate = process.required_intermediates[0]
        expression = f"{incoming} > {intermediate} > {final}"
    else:
        expression = f"{incoming} > {final}"

    expression += _render_coupling_orders(process)

    if process.excluded_particles:
        excluded = " ".join(process.excluded_particles)
        expression += f" / {excluded}"

    decay_chains = [
        _render_decay_chain(particle)
        for particle in process.final_particles
        if particle.decay_products
    ]

    if decay_chains:
        expression += ", " + ", ".join(decay_chains)

    return expression


def build_madgraph_artifact(
    workflow: WorkflowIntent,
) -> MadGraphArtifact:
    """Build deterministic MadGraph process-generation commands."""

    commands: list[str] = [_render_model_import(workflow)]

    for index, process in enumerate(workflow.processes):
        prefix = "generate" if index == 0 else "add process"
        expression = render_process_expression(process)
        commands.append(f"{prefix} {expression}")

    output_name = workflow.run.output_name or "hep_agent_output"
    commands.append(f"output {output_name}")

    return MadGraphArtifact(commands=tuple(commands))
