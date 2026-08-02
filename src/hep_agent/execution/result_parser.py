"""Deterministic parsing of completed MadGraph executions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


CROSS_SECTION_RE = re.compile(
    r"Cross-section\s*:\s*"
    r"(?P<value>[0-9.eE+-]+)\s*"
    r"\+-\s*"
    r"(?P<uncertainty>[0-9.eE+-]+)\s*"
    r"(?P<unit>pb|fb)",
    re.IGNORECASE,
)

EVENT_COUNT_RE = re.compile(
    r"Nb of events\s*:\s*(?P<count>\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MadGraphPhysicsResult:
    """Physics and event files parsed from one MG5 run."""

    cross_section_pb: float | None
    cross_section_uncertainty_pb: float | None
    event_count: int | None

    primary_lhe_file: Path | None
    warnings: tuple[str, ...]

    # Optional later simulation stages.
    showered_hepmc_file: Path | None = None
    detector_root_file: Path | None = None

    @property
    def has_physics_summary(self) -> bool:
        return (
            self.cross_section_pb is not None
            and self.event_count is not None
        )

    @property
    def has_shower_output(self) -> bool:
        return self.showered_hepmc_file is not None

    @property
    def has_detector_output(self) -> bool:
        return self.detector_root_file is not None


def _convert_to_pb(value: float, unit: str) -> float:
    if unit.lower() == "pb":
        return value

    if unit.lower() == "fb":
        return value / 1000.0

    raise ValueError(
        f"Unsupported cross-section unit: {unit}"
    )


def find_primary_lhe_file(
    execution_directory: str | Path,
) -> Path | None:
    """Find the primary unweighted parton-level LHE file."""

    root = Path(execution_directory)

    preferred = sorted(
        root.rglob("unweighted_events.lhe.gz")
    )

    if preferred:
        return preferred[0]

    uncompressed = sorted(
        root.rglob("unweighted_events.lhe")
    )

    if uncompressed:
        return uncompressed[0]

    return None


def find_showered_hepmc_file(
    execution_directory: str | Path,
) -> Path | None:
    """Find the primary Pythia8 showered HepMC file."""

    root = Path(execution_directory)

    preferred_patterns = (
        "*_pythia8_events.hepmc.gz",
        "*_pythia8_events.hepmc",
    )

    for pattern in preferred_patterns:
        matches = sorted(root.rglob(pattern))

        if matches:
            return matches[0]

    fallback_patterns = (
        "*.hepmc.gz",
        "*.hepmc",
    )

    for pattern in fallback_patterns:
        matches = sorted(root.rglob(pattern))

        if matches:
            return matches[0]

    return None


def find_detector_root_file(
    execution_directory: str | Path,
) -> Path | None:
    """Find the primary Delphes detector-level ROOT file."""

    root = Path(execution_directory)

    preferred = sorted(
        root.rglob("*_delphes_events.root")
    )

    if preferred:
        return preferred[0]

    event_root_files = sorted(
        path
        for path in root.rglob("*.root")
        if "Events" in path.parts
    )

    if event_root_files:
        return event_root_files[0]

    return None


def parse_madgraph_result(
    *,
    stdout_text: str,
    execution_directory: str | Path,
) -> MadGraphPhysicsResult:
    """Parse physics values and generated event files."""

    cross_section_pb: float | None = None
    uncertainty_pb: float | None = None
    event_count: int | None = None
    warnings: list[str] = []

    cross_section_matches = list(
        CROSS_SECTION_RE.finditer(stdout_text)
    )

    if cross_section_matches:
        match = cross_section_matches[-1]
        unit = match.group("unit")

        cross_section_pb = _convert_to_pb(
            float(match.group("value")),
            unit,
        )

        uncertainty_pb = _convert_to_pb(
            float(match.group("uncertainty")),
            unit,
        )
    else:
        warnings.append("cross_section_not_found")

    event_matches = list(
        EVENT_COUNT_RE.finditer(stdout_text)
    )

    if event_matches:
        event_count = int(
            event_matches[-1].group("count")
        )
    else:
        warnings.append("event_count_not_found")

    if (
        "Failed to access python version of LHAPDF"
        in stdout_text
    ):
        warnings.append(
            "lhapdf_python_interface_unavailable"
        )

    lhe_file = find_primary_lhe_file(
        execution_directory
    )

    if lhe_file is None:
        warnings.append(
            "primary_lhe_file_not_found"
        )

    return MadGraphPhysicsResult(
        cross_section_pb=cross_section_pb,
        cross_section_uncertainty_pb=uncertainty_pb,
        event_count=event_count,
        primary_lhe_file=lhe_file,
        showered_hepmc_file=(
            find_showered_hepmc_file(
                execution_directory
            )
        ),
        detector_root_file=(
            find_detector_root_file(
                execution_directory
            )
        ),
        warnings=tuple(warnings),
    )
