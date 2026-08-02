"""Tests for the thin semantic process compiler."""

import unittest

from hep_agent.builders import (
    build_madgraph_workflow_artifact,
)
from hep_agent.models.semantic_process import (
    SemanticPlanningError,
    compile_semantic_process_workflow,
    parse_semantic_process_command,
)


def generate_commands(
    request: str,
    command: str,
) -> list[str]:
    workflow = (
        compile_semantic_process_workflow(
            request,
            command,
        )
    )

    artifact = (
        build_madgraph_workflow_artifact(
            workflow
        )
    )

    return [
        item
        for item in artifact.commands
        if (
            item.startswith("generate ")
            or item.startswith(
                "add process "
            )
        )
    ]


class SemanticProcessTests(
    unittest.TestCase
):
    def test_simple_two_to_two(
        self,
    ) -> None:
        commands = generate_commands(
            (
                "Simulate electron-pair "
                "production at a 13 TeV "
                "proton-proton collider with "
                "100 events. Do not use "
                "Pythia8, Delphes, or "
                "MadAnalysis."
            ),
            "generate p p > e+ e-",
        )

        self.assertEqual(
            commands,
            [
                "generate p p > e+ e-"
            ],
        )

    def test_z_decay(
        self,
    ) -> None:
        commands = generate_commands(
            (
                "At a 13 TeV proton-proton "
                "collider, produce a Z boson "
                "and decay it to e+ e- with "
                "100 events. Do not use "
                "Pythia8, Delphes, or "
                "MadAnalysis."
            ),
            (
                "generate p p > z, "
                "z > e+ e-"
            ),
        )

        self.assertEqual(
            commands,
            [
                (
                    "generate p p > z, "
                    "z > e+ e-"
                )
            ],
        )

    def test_w_decay(
        self,
    ) -> None:
        commands = generate_commands(
            (
                "At a 13 TeV proton-proton "
                "collider, produce a W+ and "
                "decay it to e+ ve with "
                "100 events. Do not use "
                "Pythia8, Delphes, or "
                "MadAnalysis."
            ),
            (
                "generate p p > w+, "
                "w+ > e+ ve"
            ),
        )

        self.assertEqual(
            commands,
            [
                (
                    "generate p p > w+, "
                    "w+ > e+ ve"
                )
            ],
        )

    def test_explicit_intermediate(
        self,
    ) -> None:
        commands = generate_commands(
            (
                "Simulate p p > z > ve ve~ "
                "at 13 TeV with 100 events. "
                "Do not use Pythia8, "
                "Delphes, or MadAnalysis."
            ),
            (
                "generate p p > z > ve ve~"
            ),
        )

        self.assertEqual(
            commands,
            [
                (
                    "generate p p > z > ve ve~"
                )
            ],
        )

    def test_ambiguous_channel_is_blocked(
        self,
    ) -> None:
        with self.assertRaises(
            SemanticPlanningError
        ) as context:
            compile_semantic_process_workflow(
                (
                    "Simulate p p > e+ e- "
                    "through a z only at "
                    "13 TeV with 100 events."
                ),
                (
                    "generate p p > "
                    "e+ e-, z > e+ e-"
                ),
            )

        self.assertEqual(
            context.exception.code,
            "ambiguous_channel_request",
        )

    def test_invented_coupling_order_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            SemanticPlanningError
        ) as context:
            parse_semantic_process_command(
                (
                    "generate p p > "
                    "e+ e- QED=2"
                )
            )

        self.assertEqual(
            context.exception.code,
            "unsafe_process_expression",
        )


if __name__ == "__main__":
    unittest.main()
