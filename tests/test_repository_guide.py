"""Regression tests for portable, fresh generated repository documentation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPOSITORY_ROOT / "scripts" / "generate_repository_guide.py"
GUIDE_PATH = REPOSITORY_ROOT / "docs" / "REPOSITORY_GUIDE.md"
MANIFEST_PATH = REPOSITORY_ROOT / "docs" / "REPOSITORY_MANIFEST.json"


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "portable_repository_guide_generator", GENERATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load repository guide generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RepositoryGuideTests(unittest.TestCase):
    def test_manifest_root_and_source_commit_are_honest(self) -> None:
        module = load_generator()
        with patch.object(module, "run_git", return_value="base-commit"):
            generated = module.build_manifest([])
        checked_in = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        self.assertEqual(generated["repository_root"], ".")
        self.assertEqual(generated["source_git_commit"], "base-commit")
        self.assertEqual(checked_in["repository_root"], ".")
        self.assertIn("source_git_commit", checked_in)
        self.assertNotIn("git_commit", checked_in)

    def test_generated_inventory_is_fresh(self) -> None:
        module = load_generator()
        checked_in = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        current = module.build_manifest(module.iter_project_files())

        self.assertEqual(checked_in["file_count"], len(checked_in["files"]))
        self.assertEqual(checked_in["files"], current["files"])
        self.assertEqual(
            GUIDE_PATH.read_text(encoding="utf-8"),
            module.build_guide(checked_in),
        )
        documented = {entry["path"] for entry in checked_in["files"]}
        self.assertTrue(
            any(path.startswith("evaluation/results/published/") for path in documented)
        )
        self.assertNotIn("docs/REPOSITORY_GUIDE.md", documented)
        self.assertNotIn("docs/REPOSITORY_MANIFEST.json", documented)


if __name__ == "__main__":
    unittest.main()
