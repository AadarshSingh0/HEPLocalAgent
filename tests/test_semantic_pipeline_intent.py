"""Tests for model-led pipeline-stage interpretation on the semantic route.

These exercise the plumbing: given the model's interpreted stage intent, the
compiled workflow reflects it, and explicit deterministic anchors still win.
Whether a given local model emits the right intent for a phrase like
"turn on Pythia" is a live-model question covered by acceptance testing, not
by these unit tests.
"""

from __future__ import annotations

import unittest

from hep_agent.models.semantic_process import (
    compile_semantic_process_workflow,
    parse_semantic_planner_output,
)


def compile_with_hints(request, command, *, pythia8_hint=None, delphes_hint=None):
    return compile_semantic_process_workflow(
        request,
        command,
        pythia8_hint=pythia8_hint,
        delphes_hint=delphes_hint,
    )


BASE_REQUEST = (
    "Simulate top-pair production at a 13 TeV proton-proton "
    "collider with 100 events."
)


class SemanticPipelineIntentTests(unittest.TestCase):
    def test_output_parser_reads_structured_stage_intent(self) -> None:
        command, pythia8, delphes = parse_semantic_planner_output(
            '{"process": "generate p p > t t~", '
            '"pythia8": "on", "delphes": "off"}'
        )
        self.assertEqual(command, "generate p p > t t~")
        self.assertIs(pythia8, True)
        self.assertIs(delphes, False)

    def test_output_parser_maps_unspecified_to_none(self) -> None:
        _, pythia8, delphes = parse_semantic_planner_output(
            '{"process": "generate p p > e+ e-", '
            '"pythia8": "unspecified", "delphes": "unspecified"}'
        )
        self.assertIsNone(pythia8)
        self.assertIsNone(delphes)

    def test_output_parser_falls_back_to_bare_generate_line(self) -> None:
        command, pythia8, delphes = parse_semantic_planner_output(
            "generate p p > e+ e-"
        )
        self.assertEqual(command, "generate p p > e+ e-")
        self.assertIsNone(pythia8)
        self.assertIsNone(delphes)

    def test_output_parser_tolerates_code_fences(self) -> None:
        command, pythia8, _ = parse_semantic_planner_output(
            '```json\n{"process": "generate p p > t t~", '
            '"pythia8": "on", "delphes": "unspecified"}\n```'
        )
        self.assertEqual(command, "generate p p > t t~")
        self.assertIs(pythia8, True)

    def test_model_hint_enables_pythia_when_regex_is_silent(self) -> None:
        # The 'turn on Pythia' class: no explicit anchor, model says on.
        workflow = compile_with_hints(
            BASE_REQUEST, "generate p p > t t~", pythia8_hint=True
        )
        self.assertTrue(workflow.pipeline.pythia8)
        self.assertEqual(
            workflow.field_sources["pipeline.pythia8"].value,
            "model_inference",
        )

    def test_unspecified_stage_defaults_off_as_validated_default(self) -> None:
        workflow = compile_with_hints(
            BASE_REQUEST, "generate p p > t t~"
        )
        self.assertFalse(workflow.pipeline.pythia8)
        self.assertFalse(workflow.pipeline.delphes)
        self.assertEqual(
            workflow.field_sources["pipeline.pythia8"].value,
            "validated_default",
        )

    def test_explicit_anchor_overrides_model_hint(self) -> None:
        # Request explicitly says "no Pythia"; even if the model guessed on,
        # the deterministic anchor wins and marks it user-sourced.
        request = BASE_REQUEST + " Do not use Pythia8."
        workflow = compile_with_hints(
            request, "generate p p > t t~", pythia8_hint=True
        )
        self.assertFalse(workflow.pipeline.pythia8)
        self.assertEqual(
            workflow.field_sources["pipeline.pythia8"].value,
            "user",
        )

    def test_explicit_anchor_on_still_wins_and_is_user_sourced(self) -> None:
        request = BASE_REQUEST + " with Pythia8 and Delphes."
        workflow = compile_with_hints(
            request, "generate p p > t t~",
            pythia8_hint=False, delphes_hint=False,
        )
        self.assertTrue(workflow.pipeline.pythia8)
        self.assertTrue(workflow.pipeline.delphes)
        self.assertEqual(
            workflow.field_sources["pipeline.pythia8"].value, "user"
        )

    def test_delphes_model_hint_enables_detector_stage(self) -> None:
        workflow = compile_with_hints(
            BASE_REQUEST, "generate p p > t t~", delphes_hint=True
        )
        self.assertTrue(workflow.pipeline.delphes)
        self.assertEqual(
            workflow.field_sources["pipeline.delphes"].value,
            "model_inference",
        )


if __name__ == "__main__":
    unittest.main()
