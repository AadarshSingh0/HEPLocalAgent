"""Tests for the terminal approval interface."""

import unittest

from hep_agent.orchestration import (
    ApprovalDecision,
    ApprovalResult,
    resolve_terminal_approval,
)


class TerminalApprovalTests(unittest.TestCase):
    def test_safe_workflow_auto_confirms(self) -> None:
        approval = ApprovalResult(
            decision=ApprovalDecision.AUTO_CONFIRM,
            auto_confirm_delay_seconds=5,
        )

        calls: list[float] = []

        def no_input(timeout: float) -> None:
            calls.append(timeout)
            return None

        result = resolve_terminal_approval(
            approval,
            timed_reader=no_input,
            output_function=lambda message: None,
        )

        self.assertTrue(result)
        self.assertEqual(len(calls), 5)

    def test_cancel_during_countdown(self) -> None:
        approval = ApprovalResult(
            decision=ApprovalDecision.AUTO_CONFIRM,
            auto_confirm_delay_seconds=5,
        )

        responses = iter([None, "c"])

        result = resolve_terminal_approval(
            approval,
            timed_reader=lambda timeout: next(responses),
            output_function=lambda message: None,
        )

        self.assertFalse(result)

    def test_edit_during_countdown_cancels_execution(self) -> None:
        approval = ApprovalResult(
            decision=ApprovalDecision.AUTO_CONFIRM,
            auto_confirm_delay_seconds=5,
        )

        result = resolve_terminal_approval(
            approval,
            timed_reader=lambda timeout: "e",
            output_function=lambda message: None,
        )

        self.assertFalse(result)

    def test_explicit_confirmation_accepts_yes(self) -> None:
        approval = ApprovalResult(
            decision=ApprovalDecision.EXPLICIT_CONFIRMATION,
        )

        result = resolve_terminal_approval(
            approval,
            input_function=lambda prompt: "yes",
            output_function=lambda message: None,
        )

        self.assertTrue(result)

    def test_blocked_workflow_never_executes(self) -> None:
        approval = ApprovalResult(
            decision=ApprovalDecision.BLOCKED,
            reasons=("Validation failed.",),
        )

        result = resolve_terminal_approval(
            approval,
            output_function=lambda message: None,
        )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
