"""Deterministic natural-language parsing for energy-scan ranges.

The parser extracts only explicit numerical scan information. It does
not infer missing energies, units, processes, models, or event counts.

The remaining request is rewritten as an ordinary single-energy
request so that the existing structured workflow planner can process
the collider workflow without being confused by several energies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import ValidationError

from hep_agent.scans.energy_scan import (
    EnergyQuantity,
    EnergyRangeSpec,
)


class EnergyScanTextError(ValueError):
    """Raised when explicit scan text is present but invalid."""


@dataclass(frozen=True)
class ParsedEnergyScanText:
    """Deterministically extracted energy-scan information."""

    original_request: str
    base_request: str
    matched_range_text: str
    energy_range: EnergyRangeSpec

    @property
    def point_count(self) -> int:
        return self.energy_range.expected_point_count


_SCAN_SIGNAL_PATTERN = re.compile(
    r"""
    \b(
        scan
        | scanning
        | sweep
        | sweeping
        | vary
        | varying
        | variation
    )\b
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


_NUMBER = r"(?:\d+(?:\.\d+)?|\.\d+)"
_UNIT = r"(?:gev|tev)"


_RANGE_PATTERNS = (
    # from 1 TeV to 5 TeV in steps of 500 GeV
    # from 1 TeV to 5 TeV at a distance of 500 GeV
    re.compile(
        rf"""
        \bfrom\s+
        (?P<start>{_NUMBER})\s*
        (?P<start_unit>{_UNIT})
        \s+
        (?:to|through|up\s+to)\s+
        (?P<stop>{_NUMBER})\s*
        (?P<stop_unit>{_UNIT})
        \s+
        (?:in|with|at)\s+
        (?:a\s+)?
        (?:
            steps?
            | increments?
            | spacing
            | distance
            | intervals?
        )
        \s*
        (?:of\s+)?
        (?P<step>{_NUMBER})\s*
        (?P<step_unit>{_UNIT})
        \b
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    ),

    # from 1 TeV to 5 TeV in 500 GeV steps
    re.compile(
        rf"""
        \bfrom\s+
        (?P<start>{_NUMBER})\s*
        (?P<start_unit>{_UNIT})
        \s+
        (?:to|through|up\s+to)\s+
        (?P<stop>{_NUMBER})\s*
        (?P<stop_unit>{_UNIT})
        \s+
        (?:in|with)\s+
        (?P<step>{_NUMBER})\s*
        (?P<step_unit>{_UNIT})
        \s+
        (?:
            steps?
            | increments?
            | intervals?
        )
        \b
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    ),

    # from 1 TeV to 5 TeV every 500 GeV
    re.compile(
        rf"""
        \bfrom\s+
        (?P<start>{_NUMBER})\s*
        (?P<start_unit>{_UNIT})
        \s+
        (?:to|through|up\s+to)\s+
        (?P<stop>{_NUMBER})\s*
        (?P<stop_unit>{_UNIT})
        \s+
        every\s+
        (?P<step>{_NUMBER})\s*
        (?P<step_unit>{_UNIT})
        \b
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    ),

    # between 1 TeV and 5 TeV in steps of 500 GeV
    re.compile(
        rf"""
        \bbetween\s+
        (?P<start>{_NUMBER})\s*
        (?P<start_unit>{_UNIT})
        \s+
        and\s+
        (?P<stop>{_NUMBER})\s*
        (?P<stop_unit>{_UNIT})
        \s+
        (?:in|with|at)\s+
        (?:a\s+)?
        (?:
            steps?
            | increments?
            | spacing
            | distance
            | intervals?
        )
        \s*
        (?:of\s+)?
        (?P<step>{_NUMBER})\s*
        (?P<step_unit>{_UNIT})
        \b
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    ),
)


_SCAN_WORDING_PATTERN = re.compile(
    r"""
    \b(?:
        perform(?:ing)?
        | run(?:ning)?
        | do(?:ing)?
        | make
        | create
    )?
    \s*
    (?:an?\s+)?
    (?:
        collider\s+energy\s+scan
        | centre[-\s]of[-\s]mass\s+energy\s+scan
        | center[-\s]of[-\s]mass\s+energy\s+scan
        | energy\s+scan
        | scan\s+of\s+(?:the\s+)?(?:collider\s+)?energy
        | scan\s+(?:the\s+)?(?:collider\s+)?energy
    )
    \b
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


def _normalize_request_text(
    request: str,
) -> str:
    """Normalize boundary and repeated whitespace."""

    if not isinstance(request, str):
        raise TypeError(
            "The scan request must be a string."
        )

    normalized = " ".join(
        request.strip().split()
    )

    if not normalized:
        raise ValueError(
            "The scan request cannot be empty."
        )

    return normalized


def _clean_base_request(
    request: str,
    *,
    match_start: int,
    match_end: int,
    start: EnergyQuantity,
) -> str:
    """Replace the scan range with one representative energy."""

    replacement = (
        "at a total centre-of-mass energy of "
        f"{start.value:g} {start.unit.upper()}"
    )

    base_request = (
        request[:match_start]
        + replacement
        + request[match_end:]
    )

    base_request = _SCAN_WORDING_PATTERN.sub(
        "",
        base_request,
    )

    base_request = re.sub(
        r"\s+",
        " ",
        base_request,
    )

    base_request = re.sub(
        r"\s+([,.;:])",
        r"\1",
        base_request,
    )

    base_request = re.sub(
        r"([,.;:])(?:\s*\1)+",
        r"\1",
        base_request,
    )

    base_request = base_request.strip(
        " ,;:"
    )

    if not base_request:
        raise EnergyScanTextError(
            "The scan range was found, but no collider workflow "
            "request remained after removing it."
        )

    return base_request


def parse_energy_scan_text(
    request: str,
) -> ParsedEnergyScanText | None:
    """Extract an explicit regular energy scan from natural language.

    Returns ``None`` for ordinary single-workflow requests.

    If scan wording is present but no supported explicit range can be
    extracted, an ``EnergyScanTextError`` is raised instead of silently
    treating the request as a single-energy workflow.
    """

    normalized = _normalize_request_text(
        request
    )

    scan_signal = _SCAN_SIGNAL_PATTERN.search(
        normalized
    )

    if scan_signal is None:
        return None

    match: re.Match[str] | None = None

    for pattern in _RANGE_PATTERNS:
        match = pattern.search(normalized)

        if match is not None:
            break

    if match is None:
        raise EnergyScanTextError(
            "The request appears to ask for an energy scan, but "
            "the start energy, stop energy, and step size could "
            "not all be extracted with explicit units."
        )

    groups = match.groupdict()

    try:
        start = EnergyQuantity(
            value=float(groups["start"]),
            unit=groups["start_unit"],
        )
        stop = EnergyQuantity(
            value=float(groups["stop"]),
            unit=groups["stop_unit"],
        )
        step = EnergyQuantity(
            value=float(groups["step"]),
            unit=groups["step_unit"],
        )

        energy_range = EnergyRangeSpec(
            start=start,
            stop=stop,
            step=step,
            include_stop=True,
        )

    except (ValidationError, ValueError) as exc:
        raise EnergyScanTextError(
            str(exc)
        ) from exc

    base_request = _clean_base_request(
        normalized,
        match_start=match.start(),
        match_end=match.end(),
        start=start,
    )

    return ParsedEnergyScanText(
        original_request=normalized,
        base_request=base_request,
        matched_range_text=match.group(0),
        energy_range=energy_range,
    )
