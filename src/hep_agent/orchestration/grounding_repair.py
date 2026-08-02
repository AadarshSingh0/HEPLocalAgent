"""Safe deterministic corrections based on explicit user statements.

This layer may restore facts that were stated explicitly by the user.
It must not invent new physics or correct ambiguous final states.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from hep_agent.schemas import (
    BeamSpec,
    ModelSource,
    ParticleNode,
    WorkflowIntent,
)
from hep_agent.validation.process_request import (
    extract_explicit_process_expression,
)
from hep_agent.validation import (
    ExplicitRequestFacts,
    extract_explicit_request_facts,
    validate_request_grounding,
)


@dataclass(frozen=True)
class GroundingCorrection:
    """One deterministic correction applied to planner output."""

    path: str
    previous_value: object
    corrected_value: object
    reason: str


@dataclass(frozen=True)
class GroundingCorrectionResult:
    """Corrected workflow and an audit trail of every change."""

    workflow: WorkflowIntent
    facts: ExplicitRequestFacts
    corrections: tuple[GroundingCorrection, ...]

    @property
    def changed(self) -> bool:
        return bool(self.corrections)


def _request_constrains_intermediate(
    user_request: str,
) -> bool:
    """Whether the user explicitly constrained a mediator.

    A single process arrow describes an inclusive hard process:

        p p > e+ e-

    Two arrows or explicit mediator language constrain an
    intermediate:

        p p > z > e+ e-
        produce e+ e- through an on-shell z
    """

    text = " ".join(
        user_request.lower().split()
    )

    chained_process = bool(
        re.search(
            r"(?:->|>)[^,;\n]+(?:->|>)",
            text,
        )
    )

    mediator_language = bool(
        re.search(
            (
                r"\b(?:via|through|mediated by|"
                r"on[- ]shell|intermediate)\b"
                r"|\bdecay(?:ing|s|ed)?\s+"
                r"(?:to|into)\b"
            ),
            text,
        )
    )

    return (
        chained_process
        or mediator_language
    )


def apply_safe_grounding_corrections(
    user_request: str,
    workflow: WorkflowIntent,
) -> GroundingCorrectionResult:
    """Restore explicit low-risk facts without calling an LLM.

    This version safely corrects:

    - explicitly stated collider beams;
    - explicitly stated hard-process incoming particles;
    - removal of unrequested intermediate constraints;
    - explicitly stated collider energy;
    - explicitly stated event count;
    - explicitly stated Pythia8 and Delphes choices;
    - an explicitly stated Standard Model choice.

    Exact MadGraph-style process expressions are authoritative.
    Their incoming particles, final-state tokens, and intermediate
    channel are restored deterministically. Natural-language final
    states remain validator-controlled.
    """

    facts = extract_explicit_request_facts(user_request)
    explicit_process = (
        extract_explicit_process_expression(
            user_request
        )
    )
    corrected = workflow.model_copy(deep=True)
    corrections: list[GroundingCorrection] = []

    if facts.collider_beams is not None:
        previous_beams = tuple(
            beam.particle for beam in corrected.collider.beams
        )

        if previous_beams != facts.collider_beams:
            corrected.collider.beams = [
                BeamSpec(particle=particle)
                for particle in facts.collider_beams
            ]

            corrections.append(
                GroundingCorrection(
                    path="collider.beams",
                    previous_value=previous_beams,
                    corrected_value=facts.collider_beams,
                    reason=(
                        "Restored collider beams explicitly stated "
                        "by the user."
                    ),
                )
            )

    expected_incoming = (
        facts.process_incoming or facts.collider_beams
    )

    if expected_incoming is not None:
        previous_incoming = tuple(
            corrected.processes[0].incoming_particles
        )

        if previous_incoming != expected_incoming:
            corrected.processes[0].incoming_particles = list(
                expected_incoming
            )

            corrections.append(
                GroundingCorrection(
                    path="processes[0].incoming_particles",
                    previous_value=previous_incoming,
                    corrected_value=expected_incoming,
                    reason=(
                        "Restored incoming particles explicitly "
                        "stated by the user."
                    ),
                )
            )

    if (
        corrected.processes
        and corrected.processes[0].required_intermediates
        and not _request_constrains_intermediate(
            user_request
        )
    ):
        previous_intermediates = tuple(
            corrected
            .processes[0]
            .required_intermediates
        )

        corrected.processes[
            0
        ].required_intermediates = []

        corrections.append(
            GroundingCorrection(
                path=(
                    "processes[0]."
                    "required_intermediates"
                ),
                previous_value=(
                    previous_intermediates
                ),
                corrected_value=(),
                reason=(
                    "Removed intermediate-particle "
                    "constraints that were not explicitly "
                    "requested by the user. The inclusive "
                    "MadGraph process will include all "
                    "allowed diagrams."
                ),
            )
        )

    if explicit_process is not None:
        process = corrected.processes[0]

        previous_final = tuple(
            node.particle
            for node in process.final_particles
        )

        had_decay_trees = any(
            bool(node.decay_products)
            for node in process.final_particles
        )

        if (
            previous_final
            != explicit_process.final_particles
            or had_decay_trees
        ):
            process.final_particles = [
                ParticleNode(
                    particle=particle
                )
                for particle in (
                    explicit_process.final_particles
                )
            ]

            corrections.append(
                GroundingCorrection(
                    path=(
                        "processes[0]."
                        "final_particles"
                    ),
                    previous_value=previous_final,
                    corrected_value=(
                        explicit_process
                        .final_particles
                    ),
                    reason=(
                        "Restored the exact final-state "
                        "tokens from explicit MadGraph-style "
                        "process syntax and removed decay "
                        "trees that the user did not request."
                    ),
                )
            )

        previous_intermediates = tuple(
            process.required_intermediates
        )

        if (
            previous_intermediates
            != explicit_process
            .required_intermediates
        ):
            process.required_intermediates = list(
                explicit_process
                .required_intermediates
            )

            corrections.append(
                GroundingCorrection(
                    path=(
                        "processes[0]."
                        "required_intermediates"
                    ),
                    previous_value=(
                        previous_intermediates
                    ),
                    corrected_value=(
                        explicit_process
                        .required_intermediates
                    ),
                    reason=(
                        "Restored the exact intermediate "
                        "channel from explicit MadGraph-style "
                        "process syntax."
                    ),
                )
            )

    if facts.energy_gev is not None:
        previous_energy = corrected.collider.energy.value_gev

        if previous_energy != facts.energy_gev:
            corrected.collider.energy.value_gev = facts.energy_gev

            corrections.append(
                GroundingCorrection(
                    path="collider.energy.value_gev",
                    previous_value=previous_energy,
                    corrected_value=facts.energy_gev,
                    reason=(
                        "Restored collider energy explicitly stated "
                        "by the user."
                    ),
                )
            )

        if (
            facts.energy_meaning is not None
            and corrected.collider.energy.meaning
            != facts.energy_meaning
        ):
            previous_meaning = corrected.collider.energy.meaning.value
            corrected.collider.energy.meaning = facts.energy_meaning

            corrections.append(
                GroundingCorrection(
                    path="collider.energy.meaning",
                    previous_value=previous_meaning,
                    corrected_value=facts.energy_meaning.value,
                    reason=(
                        "Restored whether the explicit energy was "
                        "total or per beam."
                    ),
                )
            )

    if (
        facts.nevents is not None
        and corrected.run.nevents != facts.nevents
    ):
        previous_nevents = corrected.run.nevents
        corrected.run.nevents = facts.nevents

        corrections.append(
            GroundingCorrection(
                path="run.nevents",
                previous_value=previous_nevents,
                corrected_value=facts.nevents,
                reason=(
                    "Restored the event count explicitly stated by "
                    "the user."
                ),
            )
        )

    if (
        facts.pythia8 is not None
        and corrected.pipeline.pythia8 != facts.pythia8
    ):
        previous_pythia = corrected.pipeline.pythia8
        corrected.pipeline.pythia8 = facts.pythia8

        corrections.append(
            GroundingCorrection(
                path="pipeline.pythia8",
                previous_value=previous_pythia,
                corrected_value=facts.pythia8,
                reason=(
                    "Restored the user's explicit Pythia8 choice."
                ),
            )
        )

    if (
        facts.delphes is not None
        and corrected.pipeline.delphes != facts.delphes
    ):
        previous_delphes = corrected.pipeline.delphes
        corrected.pipeline.delphes = facts.delphes

        corrections.append(
            GroundingCorrection(
                path="pipeline.delphes",
                previous_value=previous_delphes,
                corrected_value=facts.delphes,
                reason=(
                    "Restored the user's explicit Delphes choice."
                ),
            )
        )

    if (
        facts.model_name == "sm"
        and corrected.model.name.lower() != "sm"
    ):
        previous_model = corrected.model.name
        corrected.model.name = "sm"
        corrected.model.source = ModelSource.BUILTIN
        corrected.model.model_path = None

        corrections.append(
            GroundingCorrection(
                path="model.name",
                previous_value=previous_model,
                corrected_value="sm",
                reason=(
                    "Restored the explicitly requested Standard Model."
                ),
            )
        )

    if corrections:
        corrected.notes = [
            "Deterministic grounding corrections were applied; "
            "see the correction audit trail."
        ]

    # Reapply correct provenance after deterministic corrections.
    corrected = validate_request_grounding(
        user_request,
        corrected,
    ).workflow

    return GroundingCorrectionResult(
        workflow=corrected,
        facts=facts,
        corrections=tuple(corrections),
    )
