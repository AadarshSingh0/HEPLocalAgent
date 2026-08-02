"""Deterministic collider-energy scan planning.

An energy scan contains one validated base workflow and several
centre-of-mass energies. It expands into independent ordinary
WorkflowIntent objects that reuse the existing execution pipeline.

The LLM may later provide a structured range such as:

    start = 1 TeV
    stop = 5 TeV
    step = 500 GeV

The numerical grid itself is always constructed deterministically.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from hep_agent.schemas import WorkflowIntent


MAX_SCAN_POINTS = 20
MAX_TOTAL_SCAN_EVENTS = 200_000


class EnergyScanPlanError(ValueError):
    """Raised when a safe energy scan cannot be constructed."""


class EnergyQuantity(BaseModel):
    """One energy value with an explicit GeV or TeV unit."""

    value: float = Field(gt=0)
    unit: Literal["gev", "tev"]

    @field_validator("unit", mode="before")
    @classmethod
    def normalize_unit(cls, value: object) -> object:
        """Accept harmless unit capitalization and surrounding space."""

        if isinstance(value, str):
            return value.strip().lower()

        return value

    @property
    def value_gev(self) -> float:
        """Return the energy expressed in GeV."""

        if self.unit == "tev":
            return self.value * 1000.0

        return self.value

    @property
    def decimal_gev(self) -> Decimal:
        """Return an exact decimal representation in GeV."""

        value = Decimal(str(self.value))

        if self.unit == "tev":
            return value * Decimal("1000")

        return value


class EnergyRangeSpec(BaseModel):
    """Inclusive or exclusive regular collider-energy range."""

    start: EnergyQuantity
    stop: EnergyQuantity
    step: EnergyQuantity

    include_stop: bool = True

    @model_validator(mode="after")
    def validate_range(self) -> "EnergyRangeSpec":
        """Validate direction, spacing and endpoint consistency."""

        start = self.start.decimal_gev
        stop = self.stop.decimal_gev
        step = self.step.decimal_gev

        if stop <= start:
            raise ValueError(
                "The scan stop energy must be greater than "
                "the start energy."
            )

        if step <= 0:
            raise ValueError(
                "The scan step must be positive."
            )

        span = stop - start

        if self.include_stop and span % step != 0:
            raise ValueError(
                "The requested inclusive endpoint is not reached "
                "by an integer number of scan steps. Change the "
                "step size, endpoint, or use an exclusive endpoint."
            )

        point_count = self.expected_point_count

        if point_count < 2:
            raise ValueError(
                "An energy scan must contain at least two points."
            )

        if point_count > MAX_SCAN_POINTS:
            raise ValueError(
                f"The scan contains {point_count} points, exceeding "
                f"the safety limit of {MAX_SCAN_POINTS}."
            )

        return self

    @property
    def expected_point_count(self) -> int:
        """Return the number of deterministic grid points."""

        start = self.start.decimal_gev
        stop = self.stop.decimal_gev
        step = self.step.decimal_gev
        span = stop - start

        complete_steps = int(span // step)

        if self.include_stop:
            return complete_steps + 1

        if span % step == 0:
            return complete_steps

        return complete_steps + 1


class EnergyScanRequest(BaseModel):
    """Structured planner output for one collider-energy scan."""

    schema_version: Literal["1.0"] = "1.0"

    base_workflow: WorkflowIntent
    energy_range: EnergyRangeSpec

    continue_on_failure: bool = True


class EnergyScanPlan(BaseModel):
    """Validated description of one collider-energy scan."""

    schema_version: Literal["1.0"] = "1.0"

    base_workflow: WorkflowIntent

    energy_points_gev: list[float] = Field(
        min_length=2,
        max_length=MAX_SCAN_POINTS,
    )

    continue_on_failure: bool = True

    @model_validator(mode="after")
    def validate_scan(self) -> "EnergyScanPlan":
        """Enforce deterministic scan-level safety constraints."""

        normalized = [
            float(value)
            for value in self.energy_points_gev
        ]

        if any(
            not math.isfinite(value)
            for value in normalized
        ):
            raise ValueError(
                "All scan energies must be finite."
            )

        if any(
            value <= 0
            for value in normalized
        ):
            raise ValueError(
                "All scan energies must be positive."
            )

        if len(set(normalized)) != len(normalized):
            raise ValueError(
                "Duplicate collider-energy points are not allowed."
            )

        if not self.base_workflow.pipeline.madgraph:
            raise ValueError(
                "An energy scan requires MadGraph execution."
            )

        total_events = (
            self.base_workflow.run.nevents
            * len(normalized)
        )

        if total_events > MAX_TOTAL_SCAN_EVENTS:
            raise ValueError(
                "The requested scan contains "
                f"{total_events} total events, exceeding the "
                f"safety limit of {MAX_TOTAL_SCAN_EVENTS}."
            )

        self.energy_points_gev = sorted(normalized)

        return self


class EnergyScanPoint(BaseModel):
    """One independently executable point in an energy scan."""

    index: int = Field(ge=0)
    energy_gev: float = Field(gt=0)

    random_seed: int = Field(gt=0)
    output_name: str = Field(min_length=1)

    workflow: WorkflowIntent


class ExpandedEnergyScan(BaseModel):
    """Complete deterministic expansion of one energy-scan plan."""

    plan: EnergyScanPlan
    points: list[EnergyScanPoint]

    @property
    def point_count(self) -> int:
        return len(self.points)

    @property
    def total_requested_events(self) -> int:
        return sum(
            point.workflow.run.nevents
            for point in self.points
        )


def generate_energy_grid(
    energy_range: EnergyRangeSpec,
) -> list[float]:
    """Generate a regular GeV grid without floating-point drift."""

    start = energy_range.start.decimal_gev
    stop = energy_range.stop.decimal_gev
    step = energy_range.step.decimal_gev

    points: list[Decimal] = []
    current = start

    if energy_range.include_stop:
        while current <= stop:
            points.append(current)
            current += step
    else:
        while current < stop:
            points.append(current)
            current += step

    if len(points) > MAX_SCAN_POINTS:
        raise EnergyScanPlanError(
            f"The scan contains {len(points)} points, exceeding "
            f"the safety limit of {MAX_SCAN_POINTS}."
        )

    return [
        float(point)
        for point in points
    ]


def build_energy_scan_plan(
    base_workflow: WorkflowIntent,
    *,
    energy_points_gev: list[float],
    continue_on_failure: bool = True,
) -> EnergyScanPlan:
    """Construct and validate one explicit-point energy scan."""

    try:
        return EnergyScanPlan(
            base_workflow=base_workflow,
            energy_points_gev=energy_points_gev,
            continue_on_failure=continue_on_failure,
        )

    except ValueError as exc:
        raise EnergyScanPlanError(
            str(exc)
        ) from exc


def build_energy_scan_plan_from_range(
    request: EnergyScanRequest,
) -> EnergyScanPlan:
    """Construct a validated scan plan from a structured range."""

    points = generate_energy_grid(
        request.energy_range
    )

    return build_energy_scan_plan(
        request.base_workflow,
        energy_points_gev=points,
        continue_on_failure=(
            request.continue_on_failure
        ),
    )


def _energy_token(energy_gev: float) -> str:
    """Create a filesystem-safe energy label."""

    if energy_gev.is_integer():
        return f"{int(energy_gev)}gev"

    text = (
        f"{energy_gev:.6f}"
        .rstrip("0")
        .rstrip(".")
        .replace(".", "p")
    )

    return f"{text}gev"


def expand_energy_scan(
    plan: EnergyScanPlan,
) -> ExpandedEnergyScan:
    """Expand a scan into ordinary independently executable workflows."""

    points: list[EnergyScanPoint] = []

    original_run = plan.base_workflow.run
    original_seed = int(
        original_run.random_seed or 0
    )

    # MG5 seed zero means automatic/random seed selection. Scans need
    # explicit reproducible and unique seeds, so zero starts at 1001.
    first_seed = (
        original_seed
        if original_seed > 0
        else 1001
    )

    base_output_name = (
        original_run.output_name
        or "hep_energy_scan"
    )

    for index, energy_gev in enumerate(
        plan.energy_points_gev
    ):
        energy = (
            plan.base_workflow
            .collider
            .energy
            .model_copy(
                update={
                    "value_gev": energy_gev,
                }
            )
        )

        collider = (
            plan.base_workflow
            .collider
            .model_copy(
                update={
                    "energy": energy,
                }
            )
        )

        random_seed = first_seed + index

        output_name = (
            f"{base_output_name}"
            f"_scan_{index + 1:03d}"
            f"_{_energy_token(energy_gev)}"
        )

        run = original_run.model_copy(
            update={
                "random_seed": random_seed,
                "output_name": output_name,
            }
        )

        workflow = (
            plan.base_workflow.model_copy(
                update={
                    "collider": collider,
                    "run": run,
                },
                deep=True,
            )
        )

        points.append(
            EnergyScanPoint(
                index=index,
                energy_gev=energy_gev,
                random_seed=random_seed,
                output_name=output_name,
                workflow=workflow,
            )
        )

    return ExpandedEnergyScan(
        plan=plan,
        points=points,
    )
