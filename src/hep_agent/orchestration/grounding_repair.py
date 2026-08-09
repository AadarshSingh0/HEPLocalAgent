"""Safe deterministic corrections based on explicit user statements.

This layer may restore facts that were stated explicitly by the user.
It must not invent new physics or correct ambiguous final states.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from hep_agent.schemas import (
    BeamSpec,
    CouplingOrderSpec,
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
    model_domain_repair_matches,
    validate_request_grounding,
)


@dataclass(frozen=True)
class GroundingCorrection:
    """One deterministic correction applied to planner output."""

    path: str
    previous_value: object
    corrected_value: object
    reason: str
    requires_confirmation: bool = False


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

    Valid MadGraph-style process expressions are authoritative. Their
    incoming particles, final-state tokens, intermediate channel, exclusions,
    and coupling-order restrictions are restored deterministically. The only
    exception is a token that is proven absent from an authoritative selected-
    model namespace: a model-proposed replacement may survive grounding only
    when it exactly matches the deterministic domain validator's suggestions.
    Natural-language final states remain validator-controlled.
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
            accepted_domain_repair = (
                explicit_process is not None
                and model_domain_repair_matches(
                    corrected,
                    requested_tokens=expected_incoming,
                    actual_tokens=previous_incoming,
                )
            )

            if accepted_domain_repair:
                corrections.append(
                    GroundingCorrection(
                        path=(
                            "processes[0]."
                            "incoming_particles"
                        ),
                        previous_value=expected_incoming,
                        corrected_value=previous_incoming,
                        reason=(
                            "Accepted a model-domain correction of "
                            "an invalid explicit incoming-particle "
                            "token because it exactly matches the "
                            "deterministic validator's suggestions."
                        ),
                        requires_confirmation=True,
                    )
                )
            else:
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

        accepted_domain_repair = (
            previous_final
            != explicit_process.final_particles
            and model_domain_repair_matches(
                corrected,
                requested_tokens=(
                    explicit_process.final_particles
                ),
                actual_tokens=previous_final,
            )
        )

        if accepted_domain_repair:
            if had_decay_trees:
                process.final_particles = [
                    ParticleNode(particle=particle)
                    for particle in previous_final
                ]

            corrections.append(
                GroundingCorrection(
                    path=(
                        "processes[0]."
                        "final_particles"
                    ),
                    previous_value=(
                        explicit_process.final_particles
                    ),
                    corrected_value=previous_final,
                    reason=(
                        "Accepted a model-domain correction of an "
                        "invalid explicit final-state token because "
                        "it exactly matches the deterministic "
                        "validator's suggestions."
                    ),
                    requires_confirmation=True,
                )
            )

        elif (
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
            accepted_domain_repair = (
                model_domain_repair_matches(
                    corrected,
                    requested_tokens=(
                        explicit_process
                        .required_intermediates
                    ),
                    actual_tokens=(
                        previous_intermediates
                    ),
                )
            )

            if accepted_domain_repair:
                corrections.append(
                    GroundingCorrection(
                        path=(
                            "processes[0]."
                            "required_intermediates"
                        ),
                        previous_value=(
                            explicit_process
                            .required_intermediates
                        ),
                        corrected_value=(
                            previous_intermediates
                        ),
                        reason=(
                            "Accepted a model-domain correction of "
                            "an invalid explicit intermediate token "
                            "because it exactly matches the "
                            "deterministic validator's suggestions."
                        ),
                        requires_confirmation=True,
                    )
                )
            else:
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

        expected_exclusions = list(
            explicit_process.excluded_particles
        )
        previous_exclusions = list(
            process.excluded_particles
        )

        if previous_exclusions != expected_exclusions:
            process.excluded_particles = expected_exclusions

            corrections.append(
                GroundingCorrection(
                    path=(
                        "processes[0]."
                        "excluded_particles"
                    ),
                    previous_value=tuple(previous_exclusions),
                    corrected_value=tuple(expected_exclusions),
                    reason=(
                        "Restored the diagram exclusions from "
                        "explicit MadGraph-style process syntax "
                        "and removed exclusions the user did not "
                        "request."
                    ),
                )
            )

        expected_coupling_orders = {
            order.name: CouplingOrderSpec(
                value=order.value,
                comparison=order.comparison,
            )
            for order in explicit_process.coupling_orders
        }
        previous_coupling_orders = {
            name: order.model_dump(mode="json")
            for name, order in process.coupling_orders.items()
        }

        if process.coupling_orders != expected_coupling_orders:
            process.coupling_orders = expected_coupling_orders

            corrections.append(
                GroundingCorrection(
                    path=(
                        "processes[0]."
                        "coupling_orders"
                    ),
                    previous_value=previous_coupling_orders,
                    corrected_value={
                        name: order.model_dump(mode="json")
                        for name, order in (
                            expected_coupling_orders.items()
                        )
                    },
                    reason=(
                        "Restored coupling-order restrictions "
                        "from explicit MadGraph-style process "
                        "syntax and removed restrictions the user "
                        "did not request."
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
