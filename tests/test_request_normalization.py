"""Tests for harmless user-request whitespace normalization."""

import unittest

from hep_agent.orchestration.preexecution import (
    normalize_user_request,
)


class RequestNormalizationTests(unittest.TestCase):
    def test_trailing_spaces_are_removed(self) -> None:
        base = "Simulate p p > e+ e- at 13 TeV."

        self.assertEqual(
            normalize_user_request(
                base + "       "
            ),
            base,
        )

    def test_boundary_newlines_are_removed(self) -> None:
        self.assertEqual(
            normalize_user_request(
                "\n\n  Generate 100 events. \n"
            ),
            "Generate 100 events.",
        )

    def test_empty_request_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_user_request(
                "   \n\t "
            )


if __name__ == "__main__":
    unittest.main()
