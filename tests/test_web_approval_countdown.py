"""Tests for automatic web-approval countdown calculations."""

import unittest

from hep_agent.ui.web_support import (
    approval_countdown_seconds,
)


class WebApprovalCountdownTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
