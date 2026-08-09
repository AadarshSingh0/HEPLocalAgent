"""Tests for failed-request validation details in the web interface."""

from types import SimpleNamespace
import unittest

from hep_agent.ui.web_support import failure_validation_issues
from hep_agent.validation import (
    ValidationIssue,
    ValidationLevel,
    ValidationReport,
)


class WebFailureIssueTests(unittest.TestCase):
    def test_artifact_error_is_shown_when_grounding_has_no_errors(
        self,
    ) -> None:
        result = SimpleNamespace(
            grounding_report=ValidationReport(issues=()),
            artifact_report=ValidationReport(
                issues=(
                    ValidationIssue(
                        code="unknown_model_particle",
                        message=(
                            "The token 'tt~' is not defined in model 'sm'."
                        ),
                        level=ValidationLevel.ERROR,
                        path=(
                            "processes[0].final_particles[0]"
                        ),
                    ),
                )
            ),
        )

        issues = failure_validation_issues(result)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["stage"], "artifact")
        self.assertEqual(
            issues[0]["code"],
            "unknown_model_particle",
        )


if __name__ == "__main__":
    unittest.main()
