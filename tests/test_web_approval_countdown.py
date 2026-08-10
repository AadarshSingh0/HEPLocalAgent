"""Tests for automatic web-approval countdown calculations."""

import unittest

from hep_agent.orchestration.approval import (
    ApprovalDecision,
    ApprovalResult,
)
from hep_agent.ui.web_support import (
    approval_countdown_seconds,
    approval_uses_automatic_countdown,
    should_start_web_execution,
)


class WebApprovalCountdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.automatic = ApprovalResult(
            decision=ApprovalDecision.AUTO_CONFIRM,
            auto_confirm_delay_seconds=5,
        )
        self.explicit = ApprovalResult(
            decision=(
                ApprovalDecision.EXPLICIT_CONFIRMATION
            ),
            reasons=("Physics changed during repair.",),
        )
        self.blocked = ApprovalResult(
            decision=ApprovalDecision.BLOCKED,
            reasons=("Artifact validation failed.",),
        )

    def test_full_countdown(self) -> None:
        self.assertEqual(
            approval_countdown_seconds(
                deadline_timestamp=105.0,
                current_timestamp=100.0,
            ),
            5,
        )

    def test_fractional_second_rounds_up(
        self,
    ) -> None:
        self.assertEqual(
            approval_countdown_seconds(
                deadline_timestamp=100.2,
                current_timestamp=100.0,
            ),
            1,
        )

    def test_expired_countdown_is_zero(
        self,
    ) -> None:
        self.assertEqual(
            approval_countdown_seconds(
                deadline_timestamp=100.0,
                current_timestamp=105.0,
            ),
            0,
        )

    def test_only_auto_confirm_uses_countdown(self) -> None:
        self.assertTrue(
            approval_uses_automatic_countdown(
                self.automatic
            )
        )
        self.assertFalse(
            approval_uses_automatic_countdown(
                self.explicit
            )
        )
        self.assertFalse(
            approval_uses_automatic_countdown(
                self.blocked
            )
        )

    def test_expired_countdown_starts_only_auto_confirm(
        self,
    ) -> None:
        self.assertTrue(
            should_start_web_execution(
                self.automatic,
                execute_requested=False,
                countdown_remaining=0,
            )
        )

    def test_unexpired_countdown_does_not_start(self) -> None:
        self.assertFalse(
            should_start_web_execution(
                self.automatic,
                execute_requested=False,
                countdown_remaining=1,
            )
        )
        self.assertFalse(
            should_start_web_execution(
                self.explicit,
                execute_requested=False,
                countdown_remaining=0,
            )
        )

    def test_explicit_confirmation_requires_button(self) -> None:
        self.assertTrue(
            should_start_web_execution(
                self.explicit,
                execute_requested=True,
                countdown_remaining=None,
            )
        )

    def test_blocked_decision_cannot_execute(self) -> None:
        self.assertFalse(
            should_start_web_execution(
                self.blocked,
                execute_requested=True,
                countdown_remaining=0,
            )
        )

    def test_missing_decision_cannot_execute(self) -> None:
        self.assertFalse(
            should_start_web_execution(
                None,
                execute_requested=True,
                countdown_remaining=0,
            )
        )


if __name__ == "__main__":
    unittest.main()
