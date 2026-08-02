"""Sequential execution and deterministic analysis of energy scans.

This module controls scan-level behavior:

- execute points sequentially;
- continue or stop after failures;
- aggregate point results;
- save CSV and JSON provenance;
- create a dependency-free SVG plot;
- identify the maximum sampled cross section;
- warn about boundary maxima and uncertainty-level ambiguity.

The caller supplies a point executor. A later adapter will connect that
callback to the existing MadGraph/MA5 end-to-end machinery.
"""

from __future__ import annotations

import csv
import json
import math
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from html import escape
from pathlib import Path
from typing import Callable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from hep_agent.scans.energy_scan import (
    EnergyScanPoint,
    ExpandedEnergyScan,
)


class ScanPointStatus(str, Enum):
    """Execution status of one energy point."""

    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class EnergyScanStatus(str, Enum):
    """Final status of a complete scan."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True)
class PointExecutionOutcome:
    """Runner-neutral outcome returned for one scan point."""

    success: bool

    cross_section_pb: float | None = None
    cross_section_uncertainty_pb: float | None = None
    generated_event_count: int | None = None

    failure_message: str | None = None
    point_record_path: str | Path | None = None


PointExecutor = Callable[
    [EnergyScanPoint],
    PointExecutionOutcome,
]

ScanProgressObserver = Callable[
    ["ScanPointResult", int, int],
    None,
]


class ScanPointResult(BaseModel):
    """Serializable result of one requested energy point."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    energy_gev: float = Field(gt=0)
    energy_tev: float = Field(gt=0)

    random_seed: int = Field(gt=0)
    output_name: str

    status: ScanPointStatus

    cross_section_pb: float | None = None
    cross_section_uncertainty_pb: float | None = None
    generated_event_count: int | None = None

    failure_message: str | None = None
    point_record_path: str | None = None


class ScanMaximumResult(BaseModel):
    """Deterministic analysis of the largest sampled cross section."""

    model_config = ConfigDict(extra="forbid")

    point_index: int = Field(ge=0)
    energy_gev: float = Field(gt=0)
    energy_tev: float = Field(gt=0)

    cross_section_pb: float
    cross_section_uncertainty_pb: float | None = None

    at_scan_boundary: bool

    runner_up_energy_gev: float | None = None
    runner_up_cross_section_pb: float | None = None
    runner_up_uncertainty_pb: float | None = None

    separation_sigma: float | None = None
    ambiguous_within_one_sigma: bool | None = None

    warnings: list[str] = Field(
        default_factory=list
    )


class EnergyScanExecutionSummary(BaseModel):
    """Complete scan-level result and provenance record."""

    model_config = ConfigDict(extra="forbid")

    record_version: str = "1.0"

    scan_id: str
    created_at_utc: str

    status: EnergyScanStatus
    continue_on_failure: bool

    requested_point_count: int = Field(ge=2)
    completed_point_count: int = Field(ge=0)
    failed_point_count: int = Field(ge=0)
    skipped_point_count: int = Field(ge=0)

    events_per_point: int = Field(gt=0)
    total_requested_events: int = Field(gt=0)
    total_generated_events: int = Field(ge=0)

    energy_points_gev: list[float]
    point_results: list[ScanPointResult]

    maximum: ScanMaximumResult | None = None

    wall_time_seconds: float = Field(ge=0)

    output_directory: str
    csv_path: str
    json_path: str
    plot_path: str | None = None


def _make_scan_id() -> str:
    """Create one unique scan identifier."""

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%S")

    suffix = uuid.uuid4().hex[:8]

    return f"scan_{timestamp}_{suffix}"


def _utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _atomic_write_text(
    path: Path,
    content: str,
) -> None:
    """Write one text file using atomic replacement."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_name(
        f".{path.name}.tmp"
    )

    try:
        temporary.write_text(
            content,
            encoding="utf-8",
        )
        os.replace(temporary, path)

    finally:
        if temporary.exists():
            temporary.unlink()


def _portable_string(
    path: str | Path | None,
) -> str | None:
    """Normalize one optional path for JSON serialization."""

    if path is None:
        return None

    return str(
        Path(path).expanduser().resolve()
    )


def _failed_result(
    point: EnergyScanPoint,
    message: str,
    *,
    point_record_path: str | Path | None = None,
) -> ScanPointResult:
    """Create one failed point result."""

    return ScanPointResult(
        index=point.index,
        energy_gev=point.energy_gev,
        energy_tev=point.energy_gev / 1000.0,
        random_seed=point.random_seed,
        output_name=point.output_name,
        status=ScanPointStatus.FAILED,
        failure_message=message,
        point_record_path=_portable_string(
            point_record_path
        ),
    )


def _skipped_result(
    point: EnergyScanPoint,
    message: str,
) -> ScanPointResult:
    """Create one skipped point result."""

    return ScanPointResult(
        index=point.index,
        energy_gev=point.energy_gev,
        energy_tev=point.energy_gev / 1000.0,
        random_seed=point.random_seed,
        output_name=point.output_name,
        status=ScanPointStatus.SKIPPED,
        failure_message=message,
    )


def _result_from_outcome(
    point: EnergyScanPoint,
    outcome: PointExecutionOutcome,
) -> ScanPointResult:
    """Convert a runner-neutral outcome into a scan result."""

    if not outcome.success:
        return _failed_result(
            point,
            outcome.failure_message
            or "The point executor reported failure.",
            point_record_path=(
                outcome.point_record_path
            ),
        )

    if outcome.cross_section_pb is None:
        return _failed_result(
            point,
            "The point execution succeeded, but no "
            "cross-section value was available.",
        )

    if not math.isfinite(
        outcome.cross_section_pb
    ):
        return _failed_result(
            point,
            "The point executor returned a non-finite "
            "cross-section value.",
        )

    uncertainty = (
        outcome.cross_section_uncertainty_pb
    )

    if uncertainty is not None:
        if (
            not math.isfinite(uncertainty)
            or uncertainty < 0
        ):
            return _failed_result(
                point,
                "The point executor returned an invalid "
                "cross-section uncertainty.",
            )

    return ScanPointResult(
        index=point.index,
        energy_gev=point.energy_gev,
        energy_tev=point.energy_gev / 1000.0,
        random_seed=point.random_seed,
        output_name=point.output_name,
        status=ScanPointStatus.COMPLETED,
        cross_section_pb=(
            outcome.cross_section_pb
        ),
        cross_section_uncertainty_pb=(
            uncertainty
        ),
        generated_event_count=(
            outcome.generated_event_count
        ),
        point_record_path=_portable_string(
            outcome.point_record_path
        ),
    )


def analyze_scan_maximum(
    point_results: list[ScanPointResult],
    *,
    requested_point_count: int,
) -> ScanMaximumResult | None:
    """Find and characterize the largest sampled cross section."""

    usable = [
        result
        for result in point_results
        if (
            result.status
            == ScanPointStatus.COMPLETED
            and result.cross_section_pb
            is not None
        )
    ]

    if not usable:
        return None

    ranked = sorted(
        usable,
        key=lambda result: (
            result.cross_section_pb,
            -result.index,
        ),
        reverse=True,
    )

    best = ranked[0]

    at_boundary = best.index in {
        0,
        requested_point_count - 1,
    }

    warnings: list[str] = []

    if at_boundary:
        warnings.append(
            "The largest sampled cross section occurs at "
            "a scan boundary. The true maximum may lie "
            "outside the requested energy range."
        )

    runner_up = (
        ranked[1]
        if len(ranked) > 1
        else None
    )

    separation_sigma: float | None = None
    ambiguous: bool | None = None

    if runner_up is not None:
        best_uncertainty = (
            best.cross_section_uncertainty_pb
        )
        runner_uncertainty = (
            runner_up
            .cross_section_uncertainty_pb
        )

        if (
            best_uncertainty is not None
            and runner_uncertainty is not None
        ):
            combined = math.sqrt(
                best_uncertainty**2
                + runner_uncertainty**2
            )

            difference = (
                best.cross_section_pb
                - runner_up.cross_section_pb
            )

            if combined > 0:
                separation_sigma = (
                    difference / combined
                )
                ambiguous = (
                    separation_sigma <= 1.0
                )

            else:
                ambiguous = difference == 0

            if ambiguous:
                warnings.append(
                    "The largest and second-largest sampled "
                    "cross sections are compatible within one "
                    "combined standard uncertainty."
                )

    return ScanMaximumResult(
        point_index=best.index,
        energy_gev=best.energy_gev,
        energy_tev=best.energy_tev,
        cross_section_pb=(
            best.cross_section_pb
        ),
        cross_section_uncertainty_pb=(
            best.cross_section_uncertainty_pb
        ),
        at_scan_boundary=at_boundary,
        runner_up_energy_gev=(
            runner_up.energy_gev
            if runner_up is not None
            else None
        ),
        runner_up_cross_section_pb=(
            runner_up.cross_section_pb
            if runner_up is not None
            else None
        ),
        runner_up_uncertainty_pb=(
            runner_up
            .cross_section_uncertainty_pb
            if runner_up is not None
            else None
        ),
        separation_sigma=separation_sigma,
        ambiguous_within_one_sigma=ambiguous,
        warnings=warnings,
    )


def _write_results_csv(
    path: Path,
    point_results: list[ScanPointResult],
) -> None:
    """Write scan points in a reusable tabular format."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_name(
        f".{path.name}.tmp"
    )

    fieldnames = [
        "index",
        "energy_gev",
        "energy_tev",
        "random_seed",
        "output_name",
        "status",
        "cross_section_pb",
        "cross_section_uncertainty_pb",
        "generated_event_count",
        "failure_message",
        "point_record_path",
    ]

    try:
        with temporary.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=fieldnames,
            )

            writer.writeheader()

            for result in point_results:
                writer.writerow(
                    {
                        **result.model_dump(
                            mode="json"
                        ),
                        "status": (
                            result.status.value
                        ),
                    }
                )

        os.replace(temporary, path)

    finally:
        if temporary.exists():
            temporary.unlink()


def _write_cross_section_svg(
    path: Path,
    point_results: list[ScanPointResult],
) -> bool:
    """Create a dependency-free cross-section-versus-energy plot."""

    usable = [
        result
        for result in point_results
        if (
            result.status
            == ScanPointStatus.COMPLETED
            and result.cross_section_pb
            is not None
        )
    ]

    if not usable:
        return False

    width = 900
    height = 560

    left = 95
    right = 40
    top = 60
    bottom = 85

    plot_width = width - left - right
    plot_height = height - top - bottom

    x_values = [
        result.energy_tev
        for result in usable
    ]
    y_values = [
        result.cross_section_pb
        for result in usable
    ]

    x_min = min(x_values)
    x_max = max(x_values)

    if x_max == x_min:
        x_min -= 0.5
        x_max += 0.5

    y_min = min(0.0, min(y_values))
    y_max = max(y_values)

    if y_max == y_min:
        y_max = y_min + 1.0

    y_padding = 0.08 * (
        y_max - y_min
    )

    y_min -= y_padding
    y_max += y_padding

    def x_pixel(value: float) -> float:
        return left + (
            (value - x_min)
            / (x_max - x_min)
        ) * plot_width

    def y_pixel(value: float) -> float:
        return top + (
            (y_max - value)
            / (y_max - y_min)
        ) * plot_height

    points_text = " ".join(
        (
            f"{x_pixel(result.energy_tev):.2f},"
            f"{y_pixel(result.cross_section_pb):.2f}"
        )
        for result in usable
        if result.cross_section_pb is not None
    )

    elements = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="white"/>',
        (
            f'<text x="{width / 2}" y="32" '
            'text-anchor="middle" '
            'font-family="sans-serif" '
            'font-size="22">'
            'Cross section versus collider energy'
            '</text>'
        ),
        (
            f'<line x1="{left}" y1="{top}" '
            f'x2="{left}" y2="{top + plot_height}" '
            'stroke="black"/>'
        ),
        (
            f'<line x1="{left}" y1="{top + plot_height}" '
            f'x2="{left + plot_width}" '
            f'y2="{top + plot_height}" '
            'stroke="black"/>'
        ),
        (
            f'<polyline points="{points_text}" '
            'fill="none" stroke="black" '
            'stroke-width="2"/>'
        ),
    ]

    for result in usable:
        assert (
            result.cross_section_pb
            is not None
        )

        x = x_pixel(result.energy_tev)
        y = y_pixel(
            result.cross_section_pb
        )

        uncertainty = (
            result.cross_section_uncertainty_pb
        )

        if uncertainty is not None:
            y_high = y_pixel(
                result.cross_section_pb
                + uncertainty
            )
            y_low = y_pixel(
                result.cross_section_pb
                - uncertainty
            )

            elements.extend(
                [
                    (
                        f'<line x1="{x:.2f}" '
                        f'y1="{y_high:.2f}" '
                        f'x2="{x:.2f}" '
                        f'y2="{y_low:.2f}" '
                        'stroke="black"/>'
                    ),
                    (
                        f'<line x1="{x - 5:.2f}" '
                        f'y1="{y_high:.2f}" '
                        f'x2="{x + 5:.2f}" '
                        f'y2="{y_high:.2f}" '
                        'stroke="black"/>'
                    ),
                    (
                        f'<line x1="{x - 5:.2f}" '
                        f'y1="{y_low:.2f}" '
                        f'x2="{x + 5:.2f}" '
                        f'y2="{y_low:.2f}" '
                        'stroke="black"/>'
                    ),
                ]
            )

        elements.append(
            (
                f'<circle cx="{x:.2f}" '
                f'cy="{y:.2f}" r="4.5" '
                'fill="black"/>'
            )
        )

    for tick_index in range(6):
        fraction = tick_index / 5

        x_value = (
            x_min
            + fraction * (x_max - x_min)
        )
        x = left + fraction * plot_width

        elements.extend(
            [
                (
                    f'<line x1="{x:.2f}" '
                    f'y1="{top + plot_height}" '
                    f'x2="{x:.2f}" '
                    f'y2="{top + plot_height + 6}" '
                    'stroke="black"/>'
                ),
                (
                    f'<text x="{x:.2f}" '
                    f'y="{top + plot_height + 25}" '
                    'text-anchor="middle" '
                    'font-family="sans-serif" '
                    'font-size="13">'
                    f'{escape(f"{x_value:g}")}'
                    '</text>'
                ),
            ]
        )

    for tick_index in range(6):
        fraction = tick_index / 5

        y_value = (
            y_min
            + fraction * (y_max - y_min)
        )
        y = y_pixel(y_value)

        elements.extend(
            [
                (
                    f'<line x1="{left - 6}" '
                    f'y1="{y:.2f}" '
                    f'x2="{left}" '
                    f'y2="{y:.2f}" '
                    'stroke="black"/>'
                ),
                (
                    f'<text x="{left - 12}" '
                    f'y="{y + 4:.2f}" '
                    'text-anchor="end" '
                    'font-family="sans-serif" '
                    'font-size="13">'
                    f'{escape(f"{y_value:.4g}")}'
                    '</text>'
                ),
            ]
        )

    elements.extend(
        [
            (
                f'<text x="{left + plot_width / 2}" '
                f'y="{height - 25}" '
                'text-anchor="middle" '
                'font-family="sans-serif" '
                'font-size="16">'
                'Centre-of-mass energy [TeV]'
                '</text>'
            ),
            (
                f'<text x="24" '
                f'y="{top + plot_height / 2}" '
                'text-anchor="middle" '
                'font-family="sans-serif" '
                'font-size="16" '
                f'transform="rotate(-90 24 '
                f'{top + plot_height / 2})">'
                'Cross section [pb]'
                '</text>'
            ),
            "</svg>",
        ]
    )

    _atomic_write_text(
        path,
        "\n".join(elements) + "\n",
    )

    return True


def execute_energy_scan(
    expanded: ExpandedEnergyScan,
    *,
    point_executor: PointExecutor,
    output_directory: str | Path = (
        "results/scans"
    ),
    scan_id: str | None = None,
    point_observer: ScanProgressObserver | None = None,
) -> EnergyScanExecutionSummary:
    """Execute all points sequentially after one scan-level approval.

    This function performs no LLM calls.

    The caller is responsible for obtaining approval before invoking
    it. Individual points do not require additional approval.
    """

    started = time.perf_counter()

    resolved_scan_id = (
        scan_id or _make_scan_id()
    )

    scan_directory = (
        Path(output_directory)
        .expanduser()
        .resolve()
        / resolved_scan_id
    )

    scan_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    point_results: list[
        ScanPointResult
    ] = []

    stop_requested = False

    for point in expanded.points:
        if stop_requested:
            skipped = _skipped_result(
                point,
                "Skipped because an earlier point failed "
                "and continue_on_failure is false.",
            )

            point_results.append(skipped)

            if point_observer is not None:
                point_observer(
                    skipped,
                    len(point_results),
                    expanded.point_count,
                )

            continue

        try:
            outcome = point_executor(point)

            result = _result_from_outcome(
                point,
                outcome,
            )

        except Exception as exc:
            result = _failed_result(
                point,
                (
                    "Point executor raised "
                    f"{type(exc).__name__}: {exc}"
                ),
            )

        point_results.append(result)

        if point_observer is not None:
            point_observer(
                result,
                len(point_results),
                expanded.point_count,
            )

        if (
            result.status
            == ScanPointStatus.FAILED
            and not expanded.plan.continue_on_failure
        ):
            stop_requested = True

    completed_count = sum(
        result.status
        == ScanPointStatus.COMPLETED
        for result in point_results
    )

    failed_count = sum(
        result.status
        == ScanPointStatus.FAILED
        for result in point_results
    )

    skipped_count = sum(
        result.status
        == ScanPointStatus.SKIPPED
        for result in point_results
    )

    if completed_count == len(
        expanded.points
    ):
        status = EnergyScanStatus.COMPLETED

    elif completed_count > 0:
        status = EnergyScanStatus.PARTIAL

    else:
        status = EnergyScanStatus.FAILED

    maximum = analyze_scan_maximum(
        point_results,
        requested_point_count=(
            expanded.point_count
        ),
    )

    csv_path = (
        scan_directory
        / "scan_results.csv"
    )

    json_path = (
        scan_directory
        / "scan_summary.json"
    )

    plot_path = (
        scan_directory
        / "cross_section_vs_energy.svg"
    )

    _write_results_csv(
        csv_path,
        point_results,
    )

    plot_created = (
        _write_cross_section_svg(
            plot_path,
            point_results,
        )
    )

    wall_time = (
        time.perf_counter()
        - started
    )

    total_generated_events = sum(
        result.generated_event_count or 0
        for result in point_results
        if (
            result.status
            == ScanPointStatus.COMPLETED
        )
    )

    summary = EnergyScanExecutionSummary(
        scan_id=resolved_scan_id,
        created_at_utc=_utc_now(),
        status=status,
        continue_on_failure=(
            expanded
            .plan
            .continue_on_failure
        ),
        requested_point_count=(
            expanded.point_count
        ),
        completed_point_count=(
            completed_count
        ),
        failed_point_count=failed_count,
        skipped_point_count=(
            skipped_count
        ),
        events_per_point=(
            expanded
            .plan
            .base_workflow
            .run
            .nevents
        ),
        total_requested_events=(
            expanded.total_requested_events
        ),
        total_generated_events=(
            total_generated_events
        ),
        energy_points_gev=[
            point.energy_gev
            for point in expanded.points
        ],
        point_results=point_results,
        maximum=maximum,
        wall_time_seconds=wall_time,
        output_directory=str(
            scan_directory
        ),
        csv_path=str(csv_path),
        json_path=str(json_path),
        plot_path=(
            str(plot_path)
            if plot_created
            else None
        ),
    )

    _atomic_write_text(
        json_path,
        json.dumps(
            summary.model_dump(
                mode="json"
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )

    return summary
