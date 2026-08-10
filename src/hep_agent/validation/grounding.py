"""Ground structured workflows in explicit facts from the user request.

This layer checks whether the planner preserved facts that the user
stated directly. It does not attempt to understand all natural language
and does not silently change the requested physics process.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from hep_agent.schemas import (
    EnergyMeaning,
    FieldSource,
    WorkflowIntent,
)
from hep_agent.validation.analysis_request import (
    validate_analysis_request_grounding,
)
from hep_agent.validation.process_request import (
    extract_explicit_process_expression,
)
from hep_agent.validation.model_domain import (
    model_domain_repair_matches,
)
from hep_agent.validation.core import (
    ValidationIssue,
    ValidationLevel,
    ValidationReport,
)


@dataclass(frozen=True)
class ExplicitRequestFacts:
    """Facts that can be extracted reliably from the original request."""

    collider_beams: tuple[str, str] | None = None
    process_incoming: tuple[str, ...] | None = None
    final_particles: tuple[str, ...] | None = None

    energy_gev: float | None = None
    energy_meaning: EnergyMeaning | None = None
    nevents: int | None = None

    pythia8: bool | None = None
    delphes: bool | None = None
    model_name: str | None = None


@dataclass(frozen=True)
class GroundingResult:
    """Grounded workflow, explicit facts, and validation report."""

    workflow: WorkflowIntent
    facts: ExplicitRequestFacts
    report: ValidationReport


FINAL_PARTICLE_PATTERNS = (
    (
        r"(?<![a-z0-9_])e\+(?![a-z0-9_])",
        "e+",
    ),
    (
        r"(?<![a-z0-9_])e-(?![a-z0-9_])",
        "e-",
    ),
    (
        r"(?<![a-z0-9_])mu\+(?![a-z0-9_])",
        "mu+",
    ),
    (
        r"(?<![a-z0-9_])mu-(?![a-z0-9_])",
        "mu-",
    ),
    (
        r"(?<![a-z0-9_])w\+(?![a-z0-9_])",
        "w+",
    ),
    (
        r"(?<![a-z0-9_])w-(?![a-z0-9_])",
        "w-",
    ),
    (r"\banti[- ]?top(?: quark)?\b|\bantitop\b", "t~"),
    (r"\btop(?: quark)?\b", "t"),
    (r"\bpositron\b", "e+"),
    (r"\belectron\b", "e-"),
    (r"\banti[- ]?muon\b|\bpositive muon\b", "mu+"),
    (r"\bmuon\b|\bnegative muon\b", "mu-"),
    (r"\bhiggs(?: boson)?\b", "h"),
    (r"\bz(?: boson)?\b", "z"),
    (r"\bw\+\b|\bpositive w(?: boson)?\b", "w+"),
    (r"\bw-\b|\bnegative w(?: boson)?\b", "w-"),
    (r"\bphoton\b", "a"),
)



def _normalize_request_text(
    text: str,
) -> str:
    """Normalize harmless whitespace before deterministic extraction.

    Line wrapping, tabs, and repeated spaces must not change the
    physics or pipeline facts extracted from a user request.
    """

    return " ".join(
        text.lower().split()
    )


def _extract_collider_beams(text: str) -> tuple[str, str] | None:
    lower = text.lower()

    if re.search(
        (
            r"\bproton[- ]proton\b"
            r"|\bpp collisions?\b"
            r"|\bp\s+p\s*(?:to|->|>)"
            r"|\bpp\s*(?:to|->|>)"
        ),
        lower,
    ):
        return ("p", "p")

    if re.search(
        r"\belectron[- ]positron\b|\be\+\s*e-\b|\be-\s*e\+\b",
        lower,
    ):
        return ("e-", "e+")

    if re.search(
        r"\bmuon[- ]antimuon\b|\bmu\+\s*mu-\b|\bmu-\s*mu\+\b",
        lower,
    ):
        return ("mu-", "mu+")

    return None


def _extract_process_incoming(
    text: str,
) -> tuple[str, ...] | None:
    lower = text.lower()

    if re.search(
        r"\bp\s+p\s*(?:to|->|>)|\bpp\s*(?:to|->|>)",
        lower,
    ):
        return ("p", "p")

    if re.search(
        r"\bq(?:uark)?\s+q(?:bar|~)\s*(?:to|->|>)",
        lower,
    ):
        return ("q", "q~")

    if re.search(
        r"\bgluon\s+gluon\s*(?:to|->|>)|\bg\s+g\s*(?:to|->|>)",
        lower,
    ):
        return ("g", "g")

    if re.search(
        r"\belectron\s+positron\s*(?:to|->|>)",
        lower,
    ):
        return ("e-", "e+")

    return None


def _extract_final_particles(
    text: str,
) -> tuple[str, ...] | None:
    """Extract particles from the sentence-level production clause.

    Later analysis phrases such as "electron-positron invariant mass"
    are deliberately excluded from hard-process final-state parsing.
    """

    normalized = _normalize_request_text(
        text
    )

    marker = re.search(
        (
            r"(?:producing|produce|into|"
            r"(?:to|->|>)\s+)"
            r"([^.!?;]+)"
        ),
        normalized,
    )

    if marker is None:
        return None

    tail = marker.group(1)

    matches: list[
        tuple[int, int, int, str]
    ] = []

    for priority, (pattern, particle) in enumerate(
        FINAL_PARTICLE_PATTERNS
    ):
        for match in re.finditer(
            pattern,
            tail,
        ):
            matches.append(
                (
                    match.start(),
                    match.end(),
                    priority,
                    particle,
                )
            )

    if not matches:
        return None

    # Specific phrases such as ``anti-top`` and ``positive muon``
    # contain shorter particle words that also match later patterns.
    # Keep the first, more specific span and discard only overlapping
    # aliases. Non-overlapping repeated particles remain intact.
    matches.sort(
        key=lambda item: (
            item[0],
            item[2],
            -(item[1] - item[0]),
        )
    )

    accepted: list[
        tuple[int, int, str]
    ] = []

    for start, end, _, particle in matches:
        overlaps = any(
            start < accepted_end
            and end > accepted_start
            for (
                accepted_start,
                accepted_end,
                _,
            ) in accepted
        )

        if overlaps:
            continue

        accepted.append(
            (start, end, particle)
        )

    accepted.sort(
        key=lambda item: item[0]
    )

    return tuple(
        particle
        for _, _, particle in accepted
    )


def _extract_energy(
    text: str,
) -> tuple[float | None, EnergyMeaning | None]:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(tev|gev)\b",
        text.lower(),
    )

    if match is None:
        return None, None

    value = float(match.group(1))
    unit = match.group(2)

    if unit == "tev":
        value *= 1000.0

    lower = text.lower()

    if re.search(r"\bper[- ]beam\b|\beach beam\b", lower):
        meaning = EnergyMeaning.PER_BEAM
    else:
        meaning = EnergyMeaning.TOTAL_CENTER_OF_MASS

    return value, meaning


def _extract_nevents(text: str) -> int | None:
    match = re.search(
        r"\b(\d[\d,]*)\s+events?\b",
        text.lower(),
    )

    if match is None:
        return None

    return int(match.group(1).replace(",", ""))


def _extract_stage_choice(
    text: str,
    stage_pattern: str,
) -> bool | None:
    """Extract a stage choice with negation scoped to that stage.

    For example, "with Pythia8 and no Delphes" enables Pythia8
    and disables Delphes rather than disabling both.
    """

    normalized = _normalize_request_text(
        text
    )

    negative_patterns = (
        (
            rf"\bno\s+"
            rf"(?:{stage_pattern})\b"
        ),
        (
            rf"\bwithout\b"
            rf"[^.!?;]{{0,60}}"
            rf"\b(?:{stage_pattern})\b"
        ),
        (
            rf"\bdo not use\b"
            rf"[^.!?;]{{0,80}}"
            rf"\b(?:{stage_pattern})\b"
        ),
        (
            rf"\bdon't use\b"
            rf"[^.!?;]{{0,80}}"
            rf"\b(?:{stage_pattern})\b"
        ),
        (
            rf"\bdisable(?:d)?\b"
            rf"[^.!?;]{{0,60}}"
            rf"\b(?:{stage_pattern})\b"
        ),
    )

    if any(
        re.search(pattern, normalized)
        for pattern in negative_patterns
    ):
        return False

    positive_patterns = (
        (
            rf"\bwith\b"
            rf"[^.!?;]{{0,60}}"
            rf"\b(?:{stage_pattern})\b"
        ),
        (
            rf"\buse\b"
            rf"[^.!?;]{{0,60}}"
            rf"\b(?:{stage_pattern})\b"
        ),
        (
            rf"\benable(?:d)?\b"
            rf"[^.!?;]{{0,60}}"
            rf"\b(?:{stage_pattern})\b"
        ),
        (
            rf"\brun(?:ning)?\b"
            rf"[^.!?;]{{0,60}}"
            rf"\b(?:{stage_pattern})\b"
        ),
    )

    if any(
        re.search(pattern, normalized)
        for pattern in positive_patterns
    ):
        return True

    return None


def extract_explicit_request_facts(
    user_request: str,
) -> ExplicitRequestFacts:
    """Extract only facts supported by conservative deterministic rules."""

    energy_gev, energy_meaning = _extract_energy(user_request)
    lower = user_request.lower()

    explicit_process = (
        extract_explicit_process_expression(
            user_request
        )
    )

    model_name: str | None = None
    if re.search(r"\bstandard model\b|\bsm model\b", lower):
        model_name = "sm"

    return ExplicitRequestFacts(
        collider_beams=_extract_collider_beams(user_request),
        process_incoming=(
            explicit_process.incoming_particles
            if explicit_process is not None
            else _extract_process_incoming(
                user_request
            )
        ),
        final_particles=(
            explicit_process.final_particles
            if explicit_process is not None
            else _extract_final_particles(
                user_request
            )
        ),
        energy_gev=energy_gev,
        energy_meaning=energy_meaning,
        nevents=_extract_nevents(user_request),
        pythia8=_extract_stage_choice(user_request, r"pythia8?"),
        delphes=_extract_stage_choice(user_request, r"delphes"),
        model_name=model_name,
    )


def _apply_explicit_provenance(
    workflow: WorkflowIntent,
    facts: ExplicitRequestFacts,
) -> WorkflowIntent:
    grounded = workflow.model_copy(deep=True)
    sources = dict(grounded.field_sources)

    if facts.model_name is not None:
        sources["model.name"] = FieldSource.USER
    elif grounded.model.name.lower() == "sm":
        sources["model.name"] = FieldSource.VALIDATED_DEFAULT

    if facts.collider_beams is not None:
        sources["collider.beams"] = FieldSource.USER

    if facts.energy_gev is not None:
        sources["collider.energy.value_gev"] = FieldSource.USER

    if (
        facts.process_incoming is not None
        or facts.final_particles is not None
        or facts.collider_beams is not None
    ):
        sources["processes"] = FieldSource.USER

    if facts.nevents is not None:
        sources["run.nevents"] = FieldSource.USER

    if facts.pythia8 is not None:
        sources["pipeline.pythia8"] = FieldSource.USER

    if facts.delphes is not None:
        sources["pipeline.delphes"] = FieldSource.USER

    grounded.field_sources = sources
    return grounded


def validate_request_grounding(
    user_request: str,
    workflow: WorkflowIntent,
) -> GroundingResult:
    """Compare explicit request facts with the planner workflow."""

    facts = extract_explicit_request_facts(user_request)
    grounded = _apply_explicit_provenance(workflow, facts)
    issues: list[ValidationIssue] = []

    actual_beams = tuple(
        beam.particle for beam in grounded.collider.beams
    )

    if (
        facts.collider_beams is not None
        and actual_beams != facts.collider_beams
    ):
        issues.append(
            ValidationIssue(
                code="explicit_collider_beam_mismatch",
                message=(
                    f"The user specified collider beams "
                    f"{facts.collider_beams}, but the planner produced "
                    f"{actual_beams}."
                ),
                level=ValidationLevel.ERROR,
                path="collider.beams",
            )
        )

    expected_incoming = (
        facts.process_incoming or facts.collider_beams
    )
    actual_incoming = tuple(
        grounded.processes[0].incoming_particles
    )

    if (
        expected_incoming is not None
        and actual_incoming != expected_incoming
        and not model_domain_repair_matches(
            grounded,
            requested_tokens=expected_incoming,
            actual_tokens=actual_incoming,
        )
    ):
        issues.append(
            ValidationIssue(
                code="explicit_process_incoming_mismatch",
                message=(
                    f"The user request implies incoming particles "
                    f"{expected_incoming}, but the planner produced "
                    f"{actual_incoming}."
                ),
                level=ValidationLevel.ERROR,
                path="processes[0].incoming_particles",
            )
        )

    if facts.final_particles is not None:
        actual_final = tuple(
            node.particle
            for node in grounded.processes[0].final_particles
        )

        if (
            Counter(actual_final)
            != Counter(facts.final_particles)
            and not model_domain_repair_matches(
                grounded,
                requested_tokens=facts.final_particles,
                actual_tokens=actual_final,
            )
        ):
            issues.append(
                ValidationIssue(
                    code="explicit_final_state_mismatch",
                    message=(
                        f"The user specified final particles "
                        f"{facts.final_particles}, but the planner "
                        f"produced {actual_final}."
                    ),
                    level=ValidationLevel.ERROR,
                    path="processes[0].final_particles",
                )
            )

    if facts.energy_gev is not None:
        actual_energy = grounded.collider.energy.value_gev

        if abs(actual_energy - facts.energy_gev) > 1e-9:
            issues.append(
                ValidationIssue(
                    code="explicit_energy_mismatch",
                    message=(
                        f"The user specified {facts.energy_gev:g} GeV, "
                        f"but the planner produced {actual_energy:g} GeV."
                    ),
                    level=ValidationLevel.ERROR,
                    path="collider.energy.value_gev",
                )
            )

        if grounded.collider.energy.meaning != facts.energy_meaning:
            issues.append(
                ValidationIssue(
                    code="explicit_energy_meaning_mismatch",
                    message=(
                        "The planner changed whether the supplied energy "
                        "is total centre-of-mass energy or per-beam energy."
                    ),
                    level=ValidationLevel.ERROR,
                    path="collider.energy.meaning",
                )
            )

    if (
        facts.nevents is not None
        and grounded.run.nevents != facts.nevents
    ):
        issues.append(
            ValidationIssue(
                code="explicit_event_count_mismatch",
                message=(
                    f"The user requested {facts.nevents} events, but "
                    f"the planner produced {grounded.run.nevents}."
                ),
                level=ValidationLevel.ERROR,
                path="run.nevents",
            )
        )

    if (
        facts.pythia8 is not None
        and grounded.pipeline.pythia8 != facts.pythia8
    ):
        issues.append(
            ValidationIssue(
                code="explicit_pythia_choice_mismatch",
                message="The planner changed the user's Pythia8 choice.",
                level=ValidationLevel.ERROR,
                path="pipeline.pythia8",
            )
        )

    if (
        facts.delphes is not None
        and grounded.pipeline.delphes != facts.delphes
    ):
        issues.append(
            ValidationIssue(
                code="explicit_delphes_choice_mismatch",
                message="The planner changed the user's Delphes choice.",
                level=ValidationLevel.ERROR,
                path="pipeline.delphes",
            )
        )

    analysis_report = (
        validate_analysis_request_grounding(
            user_request,
            grounded,
        )
    )

    issues.extend(
        analysis_report.issues
    )

    return GroundingResult(
        workflow=grounded,
        facts=facts,
        report=ValidationReport(
            issues=tuple(issues)
        ),
    )
