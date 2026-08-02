"""Tests for Streamlit request-input state decisions."""

import unittest

from hep_agent.ui.web_support import (
    should_disable_request_input,
)


class WebRequestStateTests(unittest.TestCase):
    def test_ready_workflow_waiting_for_approval_blocks_input(
        self,
    ) -> None:
        self.assertTrue(
            should_disable_request_input(
                prepared_exists=True,
                prepared_is_ready=True,
                final_result_exists=False,
            )
        )

    def test_failed_preparation_does_not_block_input(
        self,
    ) -> None:
        self.assertFalse(
            should_disable_request_input(
                prepared_exists=True,
                prepared_is_ready=False,
                final_result_exists=False,
            )
        )

    def test_completed_workflow_does_not_block_input(
        self,
    ) -> None:
        self.assertFalse(
            should_disable_request_input(
                prepared_exists=True,
                prepared_is_ready=True,
                final_result_exists=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
