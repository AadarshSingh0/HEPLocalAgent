"""Tests for the structured repair-prompt contract."""

import unittest

from hep_agent.models import (
    load_repair_prompt,
)


class RepairPromptContractTests(
    unittest.TestCase
):
    def test_analysis_repair_rules_are_present(
        self,
    ) -> None:
        prompt = load_repair_prompt()

        required_phrases = (
            "Never invent numerical values.",
            '"standard cuts"',
            'Exactly one object reference:',
            'Exactly two object references:',
            "`invariant_mass`",
            '`"cuts": []`',
            (
                "Explicit custom plotting requests "
                "require a non-null `analysis`"
            ),
        )

        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(
                    phrase,
                    prompt,
                )


if __name__ == "__main__":
    unittest.main()
