"""Deterministic MadGraph launch-workflow builder.

This module extends process generation with run settings and optional
Pythia8 and Delphes stages.

It does not execute MadGraph and does not call an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass

from hep_agent.builders.madgraph import (
    MadGraphArtifact,
    MadGraphBuildError,
    build_madgraph_artifact,
)
from hep_agent.schemas import EnergyMeaning, WorkflowIntent


SUPPORTED_TOTAL_COM_PAIRS = {
    ("p", "p"),
    ("e-", "e+"),
    ("e+", "e-"),
    ("mu-", "mu+"),
    ("mu+", "mu-"),
    ("q", "q~"),
    ("q~", "q"),
}


@dataclass(frozen=True)
class MadGraphWorkflowArtifact:
    """Complete deterministic MG5 process and launch artifact."""

    process_artifact: MadGraphArtifact
    launch_commands: tuple[str, ...]

    @property
    def commands(self) -> tuple[str, ...]:
        """Return all commands in execution order."""

        return self.process_artifact.commands + self.launch_commands

    @property
    def text(self) -> str:
        """Return a file-ready MG5 command script."""

        return "\n".join(self.commands) + "\n"


def _format_number(value: float) -> str:
    """Render a compact deterministic numerical value."""

    return f"{value:g}"


def resolve_beam_energies(
    workflow: WorkflowIntent,
) -> tuple[float, float]:
    """Convert the structured collider energy to MG5 beam energies."""

    energy = workflow.collider.energy
    beam_pair = tuple(
        beam.particle for beam in workflow.collider.beams
    )

    if energy.meaning == EnergyMeaning.PER_BEAM:
        return energy.value_gev, energy.value_gev

    if beam_pair not in SUPPORTED_TOTAL_COM_PAIRS:
        raise MadGraphBuildError(
            "Total centre-of-mass energy cannot yet be divided safely "
            f"for beam pair {beam_pair!r}. Supply an explicitly "
            "supported symmetric collider configuration."
        )

    return energy.value_gev / 2.0, energy.value_gev / 2.0


def build_launch_commands(
    workflow: WorkflowIntent,
) -> tuple[str, ...]:
    """Construct the deterministic MG5 launch block."""

    if workflow.pipeline.delphes and not workflow.pipeline.pythia8:
        raise MadGraphBuildError(
            "Delphes currently requires Pythia8 in this agent."
        )

    beam1_energy, beam2_energy = resolve_beam_energies(workflow)

    output_name = workflow.run.output_name or "hep_agent_output"
    random_seed = (
        workflow.run.random_seed
        if workflow.run.random_seed is not None
        else 0
    )

    shower = (
        "Pythia8"
        if workflow.pipeline.pythia8
        else "OFF"
    )

    detector = (
        "Delphes"
        if workflow.pipeline.delphes
        else "OFF"
    )

    return (
        "set automatic_html_opening False --no_save",
        f"launch {output_name}",
        f"shower={shower}",
        f"detector={detector}",
        "analysis=OFF",
        f"set nevents {workflow.run.nevents}",
        f"set iseed {random_seed}",
        f"set ebeam1 {_format_number(beam1_energy)}",
        f"set ebeam2 {_format_number(beam2_energy)}",
        "done",
    )


def build_madgraph_workflow_artifact(
    workflow: WorkflowIntent,
) -> MadGraphWorkflowArtifact:
    """Build the complete deterministic MG5 command workflow."""

    process_artifact = build_madgraph_artifact(workflow)
    launch_commands = build_launch_commands(workflow)

    return MadGraphWorkflowArtifact(
        process_artifact=process_artifact,
        launch_commands=launch_commands,
    )
