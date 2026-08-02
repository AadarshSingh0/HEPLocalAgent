"""Tests for minimum executable workflow requirements."""

import unittest

from hep_agent.validation.workflow_request import (
    extract_workflow_request_facts,
    validate_workflow_request_minimum,
)


class WorkflowRequestTests(
    unittest.TestCase
):
    def test_vague_collider_request_is_blocked(
        self,
    ) -> None:
        report = validate_workflow_request_minimum(
            "Run the colliders for proton proton at 13 TeV."
        )

        self.assertFalse(
            report.is_valid
        )

        self.assertEqual(
            {
                issue.code
                for issue in report.errors
            },
            {
                "missing_final_state",
                "missing_event_count",
            },
        )

    def test_complete_arrow_process_is_valid(
        self,
    ) -> None:
        report = validate_workflow_request_minimum(
            "Simulate p p > e+ e- at 13 TeV "
            "with 100 events."
        )

        self.assertTrue(
            report.is_valid
        )

    def test_producing_language_is_valid(
        self,
    ) -> None:
        report = validate_workflow_request_minimum(
            "Simulate proton-proton collisions producing "
            "an electron and positron at 13 TeV with "
            "200 events."
        )

        self.assertTrue(
            report.is_valid
        )

    def test_missing_energy_is_detected(
        self,
    ) -> None:
        report = validate_workflow_request_minimum(
            "Generate p p > h with 1000 events."
        )

        self.assertIn(
            "missing_collider_energy",
            {
                issue.code
                for issue in report.errors
            },
        )

    def test_facts_do_not_invent_final_state(
        self,
    ) -> None:
        facts = extract_workflow_request_facts(
            "Run proton proton collisions at 13 TeV "
            "with 100 events."
        )

        self.assertTrue(
            facts.initial_state_present
        )
        self.assertFalse(
            facts.final_state_present
        )


if __name__ == "__main__":
    unittest.main()
