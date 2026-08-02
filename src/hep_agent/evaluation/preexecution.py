"""Deterministic checks for frozen pre-execution evaluation scenarios."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isclose
from typing import Any, Mapping


@dataclass(frozen=True)
class EvaluationCheck:
    """One expected-versus-actual scenario check."""

    name: str
    passed: bool
    expected: Any
    actual: Any
    detail: str | None = None


@dataclass(frozen=True)
class ScenarioEvaluation:
    """Complete deterministic verdict for one prepared scenario."""

    scenario_id: str
    passed: bool
    analysis_mode: str | None
    checks: tuple[EvaluationCheck, ...]

    def model_dump(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "analysis_mode": self.analysis_mode,
            "checks": [
                asdict(check)
                for check in self.checks
            ],
        }


def _enum_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value

    return value


def _unit_value(value: Any) -> str | None:
    if value is None:
        return None

    return str(_enum_value(value))


def _float_equal(
    left: Any,
    right: Any,
) -> bool:
    try:
        return isclose(
            float(left),
            float(right),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    except (TypeError, ValueError):
        return False


def _particles(
    objects: Any,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            reference.particle
            for reference in objects
        )
    )


def _normalise_cut(cut: Any) -> dict[str, Any]:
    return {
        "observable": str(
            _enum_value(cut.observable)
        ),
        "particles": _particles(
            cut.objects
        ),
        "comparison": str(
            _enum_value(cut.comparison)
        ),
        "value": float(cut.value),
        "unit": _unit_value(cut.unit),
    }


def _normalise_histogram(
    histogram: Any,
) -> dict[str, Any]:
    return {
        "observable": str(
            _enum_value(histogram.observable)
        ),
        "particles": _particles(
            histogram.objects
        ),
        "bins": int(histogram.bins),
        "minimum": float(histogram.minimum),
        "maximum": float(histogram.maximum),
        "unit": _unit_value(histogram.unit),
    }


def _mapping_matches(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> bool:
    for key, expected_value in expected.items():
        if key not in actual:
            return False

        actual_value = actual[key]

        if key in {
            "value",
            "minimum",
            "maximum",
        }:
            if not _float_equal(
                actual_value,
                expected_value,
            ):
                return False
            continue

        if key == "particles":
            if tuple(
                sorted(actual_value)
            ) != tuple(
                sorted(expected_value)
            ):
                return False
            continue

        if actual_value != expected_value:
            return False

    return True


def _analysis_mode(
    workflow: Any,
) -> str:
    if not workflow.pipeline.madanalysis:
        return "disabled"

    if workflow.analysis is None:
        return "quicklook"

    return "custom"


def evaluate_prepared_scenario(
    prepared: Any,
    scenario: Mapping[str, Any],
) -> ScenarioEvaluation:
    """Evaluate one prepared workflow against frozen expectations."""

    scenario_id = str(scenario["id"])
    expected = scenario["expected"]

    checks: list[EvaluationCheck] = []

    expected_ready = bool(
        expected["ready"]
    )
    actual_ready = bool(
        prepared.is_ready
    )

    checks.append(
        EvaluationCheck(
            name="ready_state",
            passed=(
                actual_ready
                == expected_ready
            ),
            expected=expected_ready,
            actual=actual_ready,
        )
    )

    # A safely rejected scenario needs no deeper workflow checks.
    if not expected_ready:
        return ScenarioEvaluation(
            scenario_id=scenario_id,
            passed=all(
                check.passed
                for check in checks
            ),
            analysis_mode=None,
            checks=tuple(checks),
        )

    if not actual_ready:
        return ScenarioEvaluation(
            scenario_id=scenario_id,
            passed=False,
            analysis_mode=None,
            checks=tuple(checks),
        )

    workflow = prepared.result.workflow

    checks.append(
        EvaluationCheck(
            name="workflow_present",
            passed=workflow is not None,
            expected=True,
            actual=workflow is not None,
        )
    )

    if workflow is None:
        return ScenarioEvaluation(
            scenario_id=scenario_id,
            passed=False,
            analysis_mode=None,
            checks=tuple(checks),
        )

    if "energy_gev" in expected:
        actual_energy = (
            workflow.collider.energy.value_gev
        )

        checks.append(
            EvaluationCheck(
                name="collider_energy_gev",
                passed=_float_equal(
                    actual_energy,
                    expected["energy_gev"],
                ),
                expected=expected["energy_gev"],
                actual=actual_energy,
            )
        )

    if "nevents" in expected:
        checks.append(
            EvaluationCheck(
                name="event_count",
                passed=(
                    workflow.run.nevents
                    == expected["nevents"]
                ),
                expected=expected["nevents"],
                actual=workflow.run.nevents,
            )
        )

    for stage, expected_value in (
        expected.get(
            "pipeline",
            {},
        ).items()
    ):
        actual_value = bool(
            getattr(
                workflow.pipeline,
                stage,
            )
        )

        checks.append(
            EvaluationCheck(
                name=f"pipeline_{stage}",
                passed=(
                    actual_value
                    == bool(expected_value)
                ),
                expected=bool(expected_value),
                actual=actual_value,
            )
        )

    expected_analysis = expected.get(
        "analysis"
    )

    actual_mode = _analysis_mode(
        workflow
    )

    if expected_analysis is None:
        return ScenarioEvaluation(
            scenario_id=scenario_id,
            passed=all(
                check.passed
                for check in checks
            ),
            analysis_mode=actual_mode,
            checks=tuple(checks),
        )

    expected_mode = expected_analysis[
        "mode"
    ]

    checks.append(
        EvaluationCheck(
            name="analysis_mode",
            passed=(
                actual_mode
                == expected_mode
            ),
            expected=expected_mode,
            actual=actual_mode,
        )
    )

    if expected_mode != "custom":
        return ScenarioEvaluation(
            scenario_id=scenario_id,
            passed=all(
                check.passed
                for check in checks
            ),
            analysis_mode=actual_mode,
            checks=tuple(checks),
        )

    plan = workflow.analysis

    if plan is None:
        return ScenarioEvaluation(
            scenario_id=scenario_id,
            passed=False,
            analysis_mode=actual_mode,
            checks=tuple(checks),
        )

    actual_cuts = [
        _normalise_cut(cut)
        for cut in plan.cuts
    ]

    actual_histograms = [
        _normalise_histogram(histogram)
        for histogram in plan.histograms
    ]

    if "exact_cut_count" in expected_analysis:
        expected_count = int(
            expected_analysis[
                "exact_cut_count"
            ]
        )

        checks.append(
            EvaluationCheck(
                name="analysis_cut_count",
                passed=(
                    len(actual_cuts)
                    == expected_count
                ),
                expected=expected_count,
                actual=len(actual_cuts),
            )
        )

    if (
        "exact_histogram_count"
        in expected_analysis
    ):
        expected_count = int(
            expected_analysis[
                "exact_histogram_count"
            ]
        )

        checks.append(
            EvaluationCheck(
                name="analysis_histogram_count",
                passed=(
                    len(actual_histograms)
                    == expected_count
                ),
                expected=expected_count,
                actual=len(actual_histograms),
            )
        )

    for index, expected_cut in enumerate(
        expected_analysis.get(
            "cuts",
            [],
        ),
        start=1,
    ):
        matched = any(
            _mapping_matches(
                actual_cut,
                expected_cut,
            )
            for actual_cut in actual_cuts
        )

        checks.append(
            EvaluationCheck(
                name=f"expected_cut_{index}",
                passed=matched,
                expected=expected_cut,
                actual=actual_cuts,
            )
        )

    for index, expected_histogram in enumerate(
        expected_analysis.get(
            "histograms",
            [],
        ),
        start=1,
    ):
        matched = any(
            _mapping_matches(
                actual_histogram,
                expected_histogram,
            )
            for actual_histogram
            in actual_histograms
        )

        checks.append(
            EvaluationCheck(
                name=(
                    f"expected_histogram_{index}"
                ),
                passed=matched,
                expected=expected_histogram,
                actual=actual_histograms,
            )
        )

    return ScenarioEvaluation(
        scenario_id=scenario_id,
        passed=all(
            check.passed
            for check in checks
        ),
        analysis_mode=actual_mode,
        checks=tuple(checks),
    )
