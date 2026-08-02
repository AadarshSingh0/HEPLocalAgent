"""Ground MadAnalysis intent in explicit user instructions."""

from __future__ import annotations

import re
from dataclasses import dataclass

from hep_agent.schemas import WorkflowIntent
from hep_agent.validation.core import (
    ValidationIssue,
    ValidationLevel,
    ValidationReport,
)


@dataclass(frozen=True)
class AnalysisRequestFacts:
    """Conservative facts extracted from an analysis request."""

    madanalysis_mentioned: bool = False
    madanalysis_choice: bool | None = None
    custom_plot_requested: bool = False
    no_plots_requested: bool = False

    cut_request_present: bool = False
    no_cuts_requested: bool = False
    vague_standard_cuts: bool = False

    unsupported_code: str | None = None
    unsupported_reason: str | None = None


def _normalise(text: str) -> str:
    return " ".join(
        text.lower().split()
    )


def _matches_any(
    text: str,
    patterns: tuple[str, ...],
) -> bool:
    return any(
        re.search(pattern, text)
        for pattern in patterns
    )


def _extract_madanalysis_choice(
    text: str,
) -> bool | None:
    """Return the explicit MadAnalysis choice.

    True:
        use MadAnalysis
        with MadAnalysis
        run MadAnalysis

    False:
        do not use MadAnalysis
        without MadAnalysis
        no MadAnalysis

    None:
        MadAnalysis was not mentioned
    """

    stage = r"madanalysis(?:5)?"

    negative_patterns = (
        rf"\bno\s+(?:{stage})\b",
        (
            rf"\bwithout\b"
            rf"[^.!?;]{{0,100}}"
            rf"\b(?:{stage})\b"
        ),
        (
            rf"\bdo not use\b"
            rf"[^.!?;]{{0,120}}"
            rf"\b(?:{stage})\b"
        ),
        (
            rf"\bdon't use\b"
            rf"[^.!?;]{{0,120}}"
            rf"\b(?:{stage})\b"
        ),
        (
            rf"\bdisable(?:d)?\b"
            rf"[^.!?;]{{0,100}}"
            rf"\b(?:{stage})\b"
        ),
    )

    if any(
        re.search(
            pattern,
            text,
        )
        for pattern in negative_patterns
    ):
        return False

    positive_patterns = (
        (
            rf"\bwith\b"
            rf"[^.!?;]{{0,100}}"
            rf"\b(?:{stage})\b"
        ),
        (
            rf"\buse\b"
            rf"[^.!?;]{{0,100}}"
            rf"\b(?:{stage})\b"
        ),
        (
            rf"\brun(?:ning)?\b"
            rf"[^.!?;]{{0,100}}"
            rf"\b(?:{stage})\b"
        ),
        (
            rf"\benable(?:d)?\b"
            rf"[^.!?;]{{0,100}}"
            rf"\b(?:{stage})\b"
        ),
    )

    if any(
        re.search(
            pattern,
            text,
        )
        for pattern in positive_patterns
    ):
        return True

    # A bare mention such as:
    # "MadAnalysis to plot the invariant mass"
    # is also an explicit positive request.
    if re.search(
        rf"\b(?:{stage})\b",
        text,
    ):
        return True

    return None


def extract_analysis_request_facts(
    user_request: str,
) -> AnalysisRequestFacts:
    """Extract only reliable analysis-control statements."""

    text = _normalise(
        user_request
    )

    madanalysis_choice = (
        _extract_madanalysis_choice(
            text
        )
    )

    madanalysis_mentioned = (
        madanalysis_choice is True
    )

    no_plots_requested = _matches_any(
        text,
        (
            (
                r"\b(?:do not|don't)\s+"
                r"(?:produce|make|create|generate)\s+"
                r"(?:any\s+)?plots?\b"
            ),
            r"\bwithout\s+(?:any\s+)?plots?\b",
            r"\bno\s+plots?\b",
        ),
    )

    no_cuts_requested = _matches_any(
        text,
        (
            (
                r"\b(?:do not|don't)\s+"
                r"(?:apply|use|add|make)\s+"
                r"(?:any\s+)?"
                r"(?:selection\s+)?cuts?\b"
            ),
            (
                r"\bwithout\s+(?:any\s+)?"
                r"(?:selection\s+)?cuts?\b"
            ),
            r"\bno\s+(?:selection\s+)?cuts?\b",
        ),
    )

    vague_standard_cuts = bool(
        re.search(
            r"\bstandard\s+cuts?\b",
            text,
        )
    )

    plot_language_present = bool(
        re.search(
            r"\b(?:plot|histogram)\b",
            text,
        )
    )

    custom_plot_requested = (
        madanalysis_mentioned
        and plot_language_present
        and not no_plots_requested
    )

    cut_language_present = _matches_any(
        text,
        (
            r"\brequire\b",
            r"\bselect\b",
            r"\bapply\s+(?:standard\s+)?cuts?\b",
            r"\bselection\s+cuts?\b",
            r"\bcut\s+on\b",
        ),
    )

    cut_request_present = (
        madanalysis_mentioned
        and cut_language_present
        and not no_cuts_requested
    )

    energy_difference = _matches_any(
        text,
        (
            r"\benergy\s+difference\b",
            (
                r"\be\s*\(\s*e\+\s*\)\s*"
                r"(?:minus|-)\s*"
                r"e\s*\(\s*e-\s*\)"
            ),
            (
                r"\be\s*\(\s*e-\s*\)\s*"
                r"(?:minus|-)\s*"
                r"e\s*\(\s*e\+\s*\)"
            ),
        ),
    )

    unsupported_code: str | None = None
    unsupported_reason: str | None = None

    if energy_difference:
        unsupported_code = (
            "unsupported_energy_difference"
        )
        unsupported_reason = (
            "The structured-analysis schema does not "
            "support algebraic energy-difference observables."
        )

    elif (
        madanalysis_mentioned
        and no_plots_requested
        and cut_request_present
    ):
        unsupported_code = (
            "unsupported_cut_only_analysis"
        )
        unsupported_reason = (
            "The current structured-analysis schema "
            "requires at least one histogram and therefore "
            "cannot represent a cut-only analysis."
        )

    return AnalysisRequestFacts(
        madanalysis_mentioned=(
            madanalysis_mentioned
        ),
        madanalysis_choice=(
            madanalysis_choice
        ),
        custom_plot_requested=(
            custom_plot_requested
        ),
        no_plots_requested=(
            no_plots_requested
        ),
        cut_request_present=(
            cut_request_present
        ),
        no_cuts_requested=(
            no_cuts_requested
        ),
        vague_standard_cuts=(
            vague_standard_cuts
        ),
        unsupported_code=(
            unsupported_code
        ),
        unsupported_reason=(
            unsupported_reason
        ),
    )


def validate_analysis_request_capability(
    user_request: str,
) -> ValidationReport:
    """Reject explicitly unsupported analysis requests before planning."""

    facts = extract_analysis_request_facts(
        user_request
    )

    if facts.unsupported_code is None:
        return ValidationReport(
            issues=()
        )

    return ValidationReport(
        issues=(
            ValidationIssue(
                code=facts.unsupported_code,
                message=(
                    facts.unsupported_reason
                    or "Unsupported analysis request."
                ),
                level=ValidationLevel.ERROR,
                path="analysis",
            ),
        )
    )


def validate_analysis_request_grounding(
    user_request: str,
    workflow: WorkflowIntent,
) -> ValidationReport:
    """Check that the workflow preserved explicit analysis intent."""

    facts = extract_analysis_request_facts(
        user_request
    )
    issues: list[ValidationIssue] = []

    if facts.madanalysis_choice is None:
        return ValidationReport(
            issues=()
        )

    if facts.madanalysis_choice is False:
        if workflow.pipeline.madanalysis:
            issues.append(
                ValidationIssue(
                    code=(
                        "explicit_madanalysis_"
                        "choice_mismatch"
                    ),
                    message=(
                        "The user explicitly disabled "
                        "MadAnalysis, but the workflow "
                        "enabled it."
                    ),
                    level=ValidationLevel.ERROR,
                    path="pipeline.madanalysis",
                )
            )

        if workflow.analysis is not None:
            issues.append(
                ValidationIssue(
                    code=(
                        "explicit_no_madanalysis_"
                        "plan_violated"
                    ),
                    message=(
                        "The user explicitly disabled "
                        "MadAnalysis, but an analysis "
                        "plan was created."
                    ),
                    level=ValidationLevel.ERROR,
                    path="analysis",
                )
            )

        return ValidationReport(
            issues=tuple(issues)
        )

    if not workflow.pipeline.madanalysis:
        issues.append(
            ValidationIssue(
                code="explicit_madanalysis_disabled",
                message=(
                    "The user explicitly requested "
                    "MadAnalysis, but the workflow disabled it."
                ),
                level=ValidationLevel.ERROR,
                path="pipeline.madanalysis",
            )
        )

    plan = workflow.analysis

    if (
        facts.custom_plot_requested
        and (
            plan is None
            or not plan.histograms
        )
    ):
        issues.append(
            ValidationIssue(
                code="explicit_custom_plot_missing",
                message=(
                    "The user explicitly requested a custom "
                    "histogram, but no structured histogram "
                    "was preserved."
                ),
                level=ValidationLevel.ERROR,
                path="analysis.histograms",
            )
        )

    if (
        facts.no_plots_requested
        and plan is not None
        and plan.histograms
    ):
        issues.append(
            ValidationIssue(
                code="explicit_no_plots_violated",
                message=(
                    "The user explicitly requested no plots, "
                    "but the workflow invented histograms."
                ),
                level=ValidationLevel.ERROR,
                path="analysis.histograms",
            )
        )

    if (
        facts.no_cuts_requested
        and plan is not None
        and plan.cuts
    ):
        issues.append(
            ValidationIssue(
                code="explicit_no_cuts_violated",
                message=(
                    "The user explicitly requested no cuts, "
                    "but numerical cuts were added."
                ),
                level=ValidationLevel.ERROR,
                path="analysis.cuts",
            )
        )

    if (
        facts.vague_standard_cuts
        and plan is not None
        and plan.cuts
    ):
        issues.append(
            ValidationIssue(
                code="invented_standard_cut_thresholds",
                message=(
                    "The user requested only vague 'standard "
                    "cuts'. Numerical thresholds must not be "
                    "invented."
                ),
                level=ValidationLevel.ERROR,
                path="analysis.cuts",
            )
        )

    return ValidationReport(
        issues=tuple(issues)
    )
