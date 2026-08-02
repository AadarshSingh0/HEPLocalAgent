"""Restricted structured language for MadAnalysis 5 requests.

The schema describes physics-analysis intent. It never stores raw
MadAnalysis commands or arbitrary executable code.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


MAX_ANALYSIS_HISTOGRAMS = 20
MAX_ANALYSIS_CUTS = 20
MAX_OBJECT_RANK = 8


class StrictAnalysisModel(BaseModel):
    """Base model rejecting unknown structured-analysis fields."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class AnalysisObservable(str, Enum):
    """Initially supported deterministic MA5 observables."""

    PT = "pt"
    ETA = "eta"
    ABS_ETA = "abs_eta"
    PHI = "phi"
    ENERGY = "energy"

    INVARIANT_MASS = "invariant_mass"
    MET = "met"

    DELTA_R = "delta_r"
    DELTA_PHI = "delta_phi"


class AnalysisComparison(str, Enum):
    """Initially supported one-sided cut comparisons."""

    GREATER_THAN = ">"
    LESS_THAN = "<"


class AnalysisUnit(str, Enum):
    """Physical units stored in structured analysis provenance."""

    GEV = "GeV"
    RADIAN = "radian"
    DIMENSIONLESS = "dimensionless"


ENERGY_OBSERVABLES = {
    AnalysisObservable.PT,
    AnalysisObservable.ENERGY,
    AnalysisObservable.INVARIANT_MASS,
    AnalysisObservable.MET,
}

ANGLE_OBSERVABLES = {
    AnalysisObservable.PHI,
    AnalysisObservable.DELTA_PHI,
}

DIMENSIONLESS_OBSERVABLES = {
    AnalysisObservable.ETA,
    AnalysisObservable.ABS_ETA,
    AnalysisObservable.DELTA_R,
}

ZERO_OBJECT_OBSERVABLES = {
    AnalysisObservable.MET,
}

ONE_OBJECT_OBSERVABLES = {
    AnalysisObservable.PT,
    AnalysisObservable.ETA,
    AnalysisObservable.ABS_ETA,
    AnalysisObservable.PHI,
    AnalysisObservable.ENERGY,
}

TWO_OBJECT_OBSERVABLES = {
    AnalysisObservable.INVARIANT_MASS,
    AnalysisObservable.DELTA_R,
    AnalysisObservable.DELTA_PHI,
}


def expected_analysis_unit(
    observable: AnalysisObservable,
) -> AnalysisUnit:
    """Return the canonical unit for one supported observable."""

    if observable in ENERGY_OBSERVABLES:
        return AnalysisUnit.GEV

    if observable in ANGLE_OBSERVABLES:
        return AnalysisUnit.RADIAN

    return AnalysisUnit.DIMENSIONLESS


def required_object_count(
    observable: AnalysisObservable,
) -> int:
    """Return the number of explicit objects required."""

    if observable in ZERO_OBJECT_OBSERVABLES:
        return 0

    if observable in ONE_OBJECT_OBSERVABLES:
        return 1

    if observable in TWO_OBJECT_OBSERVABLES:
        return 2

    raise ValueError(
        f"Unsupported analysis observable: {observable}"
    )


class AnalysisObjectRef(StrictAnalysisModel):
    """One explicitly ranked MA5 particle/object reference."""

    particle: str = Field(min_length=1)
    rank: int = Field(
        default=1,
        ge=1,
        le=MAX_OBJECT_RANK,
    )

    @field_validator("particle")
    @classmethod
    def reject_unsafe_particle_label(
        cls,
        value: str,
    ) -> str:
        """Reject syntax-bearing or whitespace-containing labels."""

        forbidden = {
            "\n",
            "\r",
            ";",
            "`",
            "(",
            ")",
            "[",
            "]",
            ",",
        }

        if any(
            character in value
            for character in forbidden
        ):
            raise ValueError(
                "Analysis particle labels cannot contain "
                "MA5 syntax or unsafe characters."
            )

        if any(
            character.isspace()
            for character in value
        ):
            raise ValueError(
                "Analysis particle labels cannot contain whitespace."
            )

        return value


class AnalysisExpressionBase(StrictAnalysisModel):
    """Fields shared by histograms and cuts."""

    observable: AnalysisObservable
    # This field must be present in planner JSON.
    # MET explicitly uses objects=[], while all other observables
    # require one or two references.
    objects: list[AnalysisObjectRef] = Field(
        max_length=2,
    )
    unit: AnalysisUnit | None = None

    @model_validator(mode="before")
    @classmethod
    def add_canonical_unit(
        cls,
        data: Any,
    ) -> Any:
        """Fill a missing unit deterministically from the observable."""

        if not isinstance(data, dict):
            return data

        if data.get("unit") is not None:
            return data

        observable_value = data.get(
            "observable"
        )

        if observable_value is None:
            return data

        try:
            observable = AnalysisObservable(
                observable_value
            )
        except ValueError:
            return data

        updated = dict(data)
        updated["unit"] = (
            expected_analysis_unit(
                observable
            ).value
        )

        return updated

    @model_validator(mode="after")
    def validate_expression(
        self,
    ) -> "AnalysisExpressionBase":
        """Validate object cardinality and canonical units."""

        expected_count = required_object_count(
            self.observable
        )

        if len(self.objects) != expected_count:
            raise ValueError(
                f"Observable {self.observable.value!r} "
                f"requires exactly {expected_count} "
                "explicit object reference(s)."
            )

        expected_unit = expected_analysis_unit(
            self.observable
        )

        if self.unit != expected_unit:
            raise ValueError(
                f"Observable {self.observable.value!r} "
                f"must use unit {expected_unit.value!r}."
            )

        return self


class AnalysisHistogramSpec(
    AnalysisExpressionBase
):
    """One deterministic one-dimensional MA5 histogram."""

    histogram_id: str = Field(
        pattern=r"^[A-Za-z][A-Za-z0-9_]*$"
    )

    bins: int = Field(
        ge=1,
        le=200,
    )
    minimum: float
    maximum: float

    @model_validator(mode="after")
    def validate_axis(
        self,
    ) -> "AnalysisHistogramSpec":
        """Require a finite non-empty histogram range."""

        if not math.isfinite(
            self.minimum
        ):
            raise ValueError(
                "Histogram minimum must be finite."
            )

        if not math.isfinite(
            self.maximum
        ):
            raise ValueError(
                "Histogram maximum must be finite."
            )

        if self.maximum <= self.minimum:
            raise ValueError(
                "Histogram maximum must be greater "
                "than its minimum."
            )

        return self


class AnalysisCutSpec(
    AnalysisExpressionBase
):
    """One deterministic event-selection cut."""

    cut_id: str = Field(
        pattern=r"^[A-Za-z][A-Za-z0-9_]*$"
    )

    comparison: AnalysisComparison
    value: float

    @model_validator(mode="after")
    def validate_threshold(
        self,
    ) -> "AnalysisCutSpec":
        """Require a finite numerical threshold."""

        if not math.isfinite(self.value):
            raise ValueError(
                "Cut threshold must be finite."
            )

        return self


class AnalysisPlan(StrictAnalysisModel):
    """Complete restricted analysis request."""

    schema_version: str = "1.0"

    histograms: list[
        AnalysisHistogramSpec
    ] = Field(
        min_length=1,
        max_length=MAX_ANALYSIS_HISTOGRAMS,
    )

    cuts: list[
        AnalysisCutSpec
    ] = Field(
        default_factory=list,
        max_length=MAX_ANALYSIS_CUTS,
    )

    @model_validator(mode="after")
    def require_unique_ids(
        self,
    ) -> "AnalysisPlan":
        """Require stable unique histogram and cut identifiers."""

        histogram_ids = [
            histogram.histogram_id
            for histogram in self.histograms
        ]

        if len(histogram_ids) != len(
            set(histogram_ids)
        ):
            raise ValueError(
                "Every analysis histogram_id must be unique."
            )

        cut_ids = [
            cut.cut_id
            for cut in self.cuts
        ]

        if len(cut_ids) != len(
            set(cut_ids)
        ):
            raise ValueError(
                "Every analysis cut_id must be unique."
            )

        return self
