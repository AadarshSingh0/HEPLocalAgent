"""Conservative validation of user-supplied workflow requirements."""

from __future__ import annotations

import re
from dataclasses import dataclass

from hep_agent.validation.core import (
    ValidationIssue,
    ValidationLevel,
    ValidationReport,
)


@dataclass(frozen=True)
class WorkflowRequestFacts:
    """Explicit facts required before starting workflow planning."""

    initial_state_present: bool
    final_state_present: bool
    collider_energy_present: bool
    event_count_present: bool


_PROCESS_ARROW_PATTERN = re.compile(
    r"""
    \b
    [a-z0-9+~_-]+
    (?:\s+[a-z0-9+~_-]+){0,3}
    \s*(?:->|>)\s*
    [a-z0-9+~_-]+
    """,
    re.IGNORECASE | re.VERBOSE,
)

_INITIAL_STATE_PATTERN = re.compile(
    r"""
    (?:
        \bpp\b
        | \bp\s+p\b
        | \bproton[\s-]+proton\b
        | \be\+\s*e-\b
        | \be-\s*e\+\b
        | \bmu\+\s*mu-\b
        | \bmu-\s*mu\+\b
        | \bproton[\s-]+electron\b
        | \belectron[\s-]+proton\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_PRODUCING_PATTERN = re.compile(
    r"""
    \b
    (?:
        producing
        | produce
        | final[\s-]+state(?:\s+of)?
        | decaying\s+(?:to|into)
    )
    \s+
    (?:an?\s+|the\s+)?
    [a-z0-9+~_-]+
    """,
    re.IGNORECASE | re.VERBOSE,
)

_COLLIDER_TO_PATTERN = re.compile(
    r"""
    (?:
        \bpp\b
        | \bp\s+p\b
        | \bproton[\s-]+proton\b
        | \be\+\s*e-\b
        | \bmu\+\s*mu-\b
    )
    \s+
    (?:to|into)
    \s+
    [a-z0-9+~_-]+
    """,
    re.IGNORECASE | re.VERBOSE,
)

_ENERGY_PATTERN = re.compile(
    r"""
    \b
    \d+(?:\.\d+)?
    \s*
    (?:tev|gev)
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_EVENT_COUNT_PATTERN = re.compile(
    r"""
    (?:
        \b
        \d[\d,_]*
        \s+
        events?
        \b
        |
        \b
        nevents?
        \s*(?:=|:)\s*
        \d[\d,_]*
        \b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def extract_workflow_request_facts(
    user_request: str,
) -> WorkflowRequestFacts:
    """Extract only explicitly stated executable requirements."""

    text = " ".join(
        user_request.lower().split()
    )

    process_arrow = bool(
        _PROCESS_ARROW_PATTERN.search(text)
    )

    initial_state_present = bool(
        process_arrow
        or _INITIAL_STATE_PATTERN.search(text)
    )

    final_state_present = bool(
        process_arrow
        or _PRODUCING_PATTERN.search(text)
        or _COLLIDER_TO_PATTERN.search(text)
    )

    collider_energy_present = bool(
        _ENERGY_PATTERN.search(text)
    )

    event_count_present = bool(
        _EVENT_COUNT_PATTERN.search(text)
    )

    return WorkflowRequestFacts(
        initial_state_present=(
            initial_state_present
        ),
        final_state_present=(
            final_state_present
        ),
        collider_energy_present=(
            collider_energy_present
        ),
        event_count_present=(
            event_count_present
        ),
    )


def validate_workflow_request_minimum(
    user_request: str,
) -> ValidationReport:
    """Reject incomplete executable requests before any LLM call."""

    facts = extract_workflow_request_facts(
        user_request
    )

    issues: list[ValidationIssue] = []

    if not facts.initial_state_present:
        issues.append(
            ValidationIssue(
                code="missing_initial_state",
                message=(
                    "Specify the incoming particles or collider "
                    "beams, for example `p p`."
                ),
                level=ValidationLevel.ERROR,
                path="request.initial_state",
            )
        )

    if not facts.final_state_present:
        issues.append(
            ValidationIssue(
                code="missing_final_state",
                message=(
                    "Specify the process or final state, for example "
                    "`p p > h` or `p p > e+ e-`."
                ),
                level=ValidationLevel.ERROR,
                path="request.final_state",
            )
        )

    if not facts.collider_energy_present:
        issues.append(
            ValidationIssue(
                code="missing_collider_energy",
                message=(
                    "Specify the collider energy, for example "
                    "`13 TeV`."
                ),
                level=ValidationLevel.ERROR,
                path="request.collider_energy",
            )
        )

    if not facts.event_count_present:
        issues.append(
            ValidationIssue(
                code="missing_event_count",
                message=(
                    "Specify the number of events, for example "
                    "`1000 events`."
                ),
                level=ValidationLevel.ERROR,
                path="request.event_count",
            )
        )

    return ValidationReport(
        issues=tuple(issues)
    )
