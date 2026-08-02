"""Tests for doctor report models and rendering."""

import unittest
from pathlib import Path

from hep_agent.doctor.models import (
    CheckStatus,
    DoctorCheck,
    DoctorReport,
)
from hep_agent.doctor.render import (
    render_text_report,
)


class DoctorReportTests(unittest.TestCase):
    def test_healthy_report_has_no_failures(
        self,
    ) -> None:
        report = DoctorReport.create(
            project_root=Path("/tmp/project"),
            selected_profile="qwen_primary",
            deep_checks=False,
            checks=[
                DoctorCheck(
                    check_id="python",
                    label="Python",
                    status=CheckStatus.PASS,
                    summary="Available.",
                ),
                DoctorCheck(
                    check_id="optional",
                    label="Optional tool",
                    status=CheckStatus.WARNING,
                    summary="Not configured.",
                    required=False,
                ),
            ],
        )

        self.assertTrue(report.healthy)
        self.assertEqual(
            len(report.passes),
            1,
        )
        self.assertEqual(
            len(report.warnings),
            1,
        )
        self.assertEqual(
            len(report.failures),
            0,
        )

    def test_failure_makes_report_unhealthy(
        self,
    ) -> None:
        report = DoctorReport.create(
            project_root=Path("/tmp/project"),
            selected_profile="qwen_primary",
            deep_checks=False,
            checks=[
                DoctorCheck(
                    check_id="mg5",
                    label="MG5",
                    status=CheckStatus.FAILURE,
                    summary="Missing.",
                )
            ],
        )

        self.assertFalse(report.healthy)

        payload = report.to_dict()

        self.assertFalse(
            payload["healthy"]
        )
        self.assertEqual(
            payload["summary"]["failures"],
            1,
        )

    def test_text_renderer_includes_summary(
        self,
    ) -> None:
        report = DoctorReport.create(
            project_root=Path("/tmp/project"),
            selected_profile="qwen_primary",
            deep_checks=True,
            checks=[
                DoctorCheck(
                    check_id="ollama",
                    label="Ollama",
                    status=CheckStatus.PASS,
                    summary="Reachable.",
                )
            ],
        )

        text = render_text_report(
            report
        )

        self.assertIn(
            "HEP AGENT DOCTOR",
            text,
        )
        self.assertIn(
            "[PASS] Ollama",
            text,
        )
        self.assertIn(
            "Overall: HEALTHY",
            text,
        )


if __name__ == "__main__":
    unittest.main()
