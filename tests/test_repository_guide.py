"""Regression tests for portable generated repository documentation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPOSITORY_ROOT / "scripts" / "generate_repository_guide.py"
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
    def test_manifest_root_is_portable(self) -> None:
        module = load_generator()
        with patch.object(module, "run_git", return_value="test"):
            generated = module.build_manifest([])
        checked_in = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        self.assertEqual(generated["repository_root"], ".")
        self.assertEqual(checked_in["repository_root"], ".")


if __name__ == "__main__":
    unittest.main()
