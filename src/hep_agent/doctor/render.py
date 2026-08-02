"""Text rendering for doctor reports."""

from __future__ import annotations

from hep_agent.doctor.models import (
    CheckStatus,
    DoctorReport,
)


STATUS_SYMBOLS = {
    CheckStatus.PASS: "PASS",
    CheckStatus.WARNING: "WARN",
    CheckStatus.FAILURE: "FAIL",
}


def render_text_report(
    report: DoctorReport,
) -> str:
    """Render a readable terminal report."""

    lines = [
        "=" * 78,
        "HEP AGENT DOCTOR",
        "=" * 78,
        f"Project:  {report.project_root}",
        f"Profile:  {report.selected_profile}",
        (
            "Mode:     deep"
            if report.deep_checks
            else "Mode:     standard"
        ),
        "",
    ]

    for check in report.checks:
        symbol = STATUS_SYMBOLS[
            check.status
        ]

        optional = (
            " (optional)"
            if not check.required
            else ""
        )

        lines.append(
            f"[{symbol}] {check.label}{optional}"
        )
        lines.append(
            f"       {check.summary}"
        )

        if check.details:
            for key, value in (
                check.details.items()
            ):
                lines.append(
                    f"       {key}: {value}"
                )

        if check.remediation:
            lines.append(
                "       Fix: "
                f"{check.remediation}"
            )

        lines.append("")

    lines.extend(
        [
            "-" * 78,
            (
                f"Passed: {len(report.passes)}  "
                f"Warnings: {len(report.warnings)}  "
                f"Failures: {len(report.failures)}"
            ),
            (
                "Overall: HEALTHY"
                if report.healthy
                else "Overall: ACTION REQUIRED"
            ),
            "=" * 78,
        ]
    )

    return "\n".join(lines)
