"""Tests for the local HEP-agent command parser."""

import tempfile
import unittest
from pathlib import Path

from hep_agent.ui.cli import (
    build_parser,
    combine_request_parts,
    load_json_object,
    resolve_project_path,
)


class CliTests(unittest.TestCase):
    def test_unquoted_request_words_are_combined(self) -> None:
        request = combine_request_parts(
            [
                "Simulate",
                "proton-proton",
                "collisions",
            ]
        )

        self.assertEqual(
            request,
            "Simulate proton-proton collisions",
        )

    def test_run_parser_uses_qwen_profile_by_default(
        self,
    ) -> None:
        parser = build_parser()

        args = parser.parse_args(
            [
                "run",
                "Generate",
                "ten",
                "events",
            ]
        )

        self.assertEqual(
            args.profile,
            "qwen_primary",
        )
        self.assertEqual(
            combine_request_parts(args.request),
            "Generate ten events",
        )

    def test_relative_path_uses_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            resolved = resolve_project_path(
                root,
                "configs/test.json",
            )

            self.assertEqual(
                resolved,
                root / "configs" / "test.json",
            )

    def test_json_configuration_must_be_object(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(
                '["not", "an", "object"]',
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_json_object(path)


if __name__ == "__main__":
    unittest.main()
