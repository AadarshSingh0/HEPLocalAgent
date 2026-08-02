"""Tests for validated external-execution outcomes."""

import unittest
from types import SimpleNamespace

from hep_agent.execution.outcome import (
    execution_has_valid_physics_output,
)


class ExecutionOutcomeTests(
    unittest.TestCase
):
    def test_subprocess_failure_is_failure(
        self,
    ) -> None:
        execution = SimpleNamespace(
            success=False
        )
        physics = SimpleNamespace(
            has_physics_summary=True
        )

        self.assertFalse(
            execution_has_valid_physics_output(
                execution,
                physics,
            )
        )

    def test_missing_parser_result_is_failure(
        self,
    ) -> None:
        execution = SimpleNamespace(
            success=True
        )

        self.assertFalse(
            execution_has_valid_physics_output(
                execution,
                None,
            )
        )

    def test_missing_physics_summary_is_failure(
        self,
    ) -> None:
        execution = SimpleNamespace(
            success=True
        )
        physics = SimpleNamespace(
            has_physics_summary=False
        )

        self.assertFalse(
            execution_has_valid_physics_output(
                execution,
                physics,
            )
        )

    def test_valid_physics_summary_is_success(
        self,
    ) -> None:
        execution = SimpleNamespace(
            success=True
        )
        physics = SimpleNamespace(
            has_physics_summary=True
        )

        self.assertTrue(
            execution_has_valid_physics_output(
                execution,
                physics,
            )
        )


if __name__ == "__main__":
    unittest.main()
