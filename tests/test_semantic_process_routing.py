"""Tests for explicit-versus-semantic production routing."""

import unittest

from hep_agent.orchestration.preexecution import (
    _should_use_semantic_process_planner,
)


class SemanticProcessRoutingTests(
    unittest.TestCase
):
    def test_explicit_two_to_two_uses_existing_route(
        self,
    ) -> None:
        self.assertFalse(
            _should_use_semantic_process_planner(
                (
                    "Simulate p p > e+ e- at "
                    "13 TeV with 100 events."
                )
            )
        )

    def test_explicit_two_to_three_uses_existing_route(
        self,
    ) -> None:
        self.assertFalse(
            _should_use_semantic_process_planner(
                (
                    "Simulate p p > t t~ j at "
                    "13 TeV with 100 events."
                )
            )
        )

    def test_explicit_intermediate_uses_existing_route(
        self,
    ) -> None:
        self.assertFalse(
            _should_use_semantic_process_planner(
                (
                    "Simulate p p > z > ve ve~ at "
                    "13 TeV with 100 events."
                )
            )
        )

    def test_natural_language_process_uses_semantic_route(
        self,
    ) -> None:
        self.assertTrue(
            _should_use_semantic_process_planner(
                (
                    "Produce an electron pair at a "
                    "13 TeV proton collider with "
                    "100 events."
                )
            )
        )

    def test_natural_language_decay_uses_semantic_route(
        self,
    ) -> None:
        self.assertTrue(
            _should_use_semantic_process_planner(
                (
                    "Simulate p p > z at 13 TeV "
                    "with 100 events, with the z "
                    "decaying to e+ e-."
                )
            )
        )

    def test_ambiguous_channel_uses_semantic_block(
        self,
    ) -> None:
        self.assertTrue(
            _should_use_semantic_process_planner(
                (
                    "Simulate p p > e+ e- through "
                    "a z only at 13 TeV with "
                    "100 events."
                )
            )
        )

    def test_custom_analysis_uses_full_route(
        self,
    ) -> None:
        self.assertFalse(
            _should_use_semantic_process_planner(
                (
                    "Simulate p p > e+ e- at "
                    "13 TeV with 100 events and "
                    "use MadAnalysis to plot the "
                    "invariant mass."
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
