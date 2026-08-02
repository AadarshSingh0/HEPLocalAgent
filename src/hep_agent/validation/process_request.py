"""Parse explicit MadGraph-style process syntax from user requests."""

from __future__ import annotations

import re
from dataclasses import dataclass


# Preserve arbitrary MadGraph/UFO-style particle aliases such as:
# e+, t~, j, zp, x1, n2, chi0, etc.
_PARTICLE_TOKEN = (
    r"[A-Za-z]"
    r"[A-Za-z0-9_+~.\-]*"
)

_PROCESS_PATTERN = re.compile(
    rf"""
    (?<!\S)
    (?P<incoming_1>{_PARTICLE_TOKEN})
    \s+
    (?P<incoming_2>{_PARTICLE_TOKEN})
    \s*
    (?P<arrow>->|>)
    \s*
    (?P<right>[^.!?;\n]+)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_ARROW_PATTERN = re.compile(
    r"\s*(?:->|>)\s*"
)

_TOKEN_PATTERN = re.compile(
    _PARTICLE_TOKEN
)

# These clauses mark the end of the physics process rather than
# additional final-state particles.
_TRAILING_CLAUSE_PATTERNS = (
    re.compile(
        r"""
        \s+
        (?:at|with)
        \s+
        (?:
            (?:a|the)\s+
        )?
        (?:
            (?:total\s+)?
            (?:centre|center)
            (?:[-\s]+of[-\s]+mass)?
            (?:\s+energy)?
            (?:\s+of)?
            \s+
        )?
        \d+(?:\.\d+)?
        \s*
        (?:tev|gev)
        \b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    re.compile(
        r"\s+with\s+\d[\d,_]*\s+events?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s+(?:do\s+not|don't)\s+use\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s+without\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s+using\b",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class ExplicitProcessExpression:
    """One explicit 2→N process expression."""

    incoming_particles: tuple[str, str]
    final_particles: tuple[str, ...]
    required_intermediates: tuple[str, ...]


def _strip_trailing_request_clauses(
    text: str,
) -> str:
    """Remove energy, event-count, and pipeline clauses."""

    stop_positions: list[int] = []

    for pattern in _TRAILING_CLAUSE_PATTERNS:
        match = pattern.search(text)

        if match is not None:
            stop_positions.append(
                match.start()
            )

    if stop_positions:
        text = text[
            : min(stop_positions)
        ]

    return text.strip(
        " \t,:"
    )


def _particle_tokens(
    text: str,
) -> tuple[str, ...]:
    return tuple(
        match.group(0)
        for match in _TOKEN_PATTERN.finditer(
            text
        )
    )


def extract_explicit_process_expression(
    user_request: str,
) -> ExplicitProcessExpression | None:
    """Extract explicit 2→N or 2→X→N syntax.

    Examples:

        p p > e+ e-
        p p > e+ e- j
        q q > u u
        p p > z > e+ e-
    """

    normalized = " ".join(
        user_request.strip().split()
    )

    match = _PROCESS_PATTERN.search(
        normalized
    )

    if match is None:
        return None

    incoming = (
        match.group("incoming_1"),
        match.group("incoming_2"),
    )

    right = _strip_trailing_request_clauses(
        match.group("right")
    )

    parts = [
        part.strip()
        for part in _ARROW_PATTERN.split(
            right
        )
        if part.strip()
    ]

    if not parts:
        return None

    final_particles = _particle_tokens(
        parts[-1]
    )

    if not final_particles:
        return None

    required_intermediates: list[str] = []

    for intermediate_part in parts[:-1]:
        required_intermediates.extend(
            _particle_tokens(
                intermediate_part
            )
        )

    return ExplicitProcessExpression(
        incoming_particles=incoming,
        final_particles=final_particles,
        required_intermediates=tuple(
            required_intermediates
        ),
    )
