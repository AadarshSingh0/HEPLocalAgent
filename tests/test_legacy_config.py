"""Regression tests for portable legacy-baseline runtime configuration."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPOSITORY_ROOT / "legacy_baseline" / "config.py"
BOOTSTRAP_PATH = (
    REPOSITORY_ROOT / "legacy_baseline" / "core" / "bootstrap.py"
)


def load_legacy_config():
    spec = importlib.util.spec_from_file_location(
        "legacy_baseline_portable_config", CONFIG_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load legacy_baseline/config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_legacy_bootstrap(ma5_path: str):
    config_module = types.ModuleType("config")
    config_module.MA5_PATH = ma5_path
    spec = importlib.util.spec_from_file_location(
        "legacy_baseline_portable_bootstrap", BOOTSTRAP_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load legacy_baseline/core/bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"config": config_module}):
        spec.loader.exec_module(module)
    return module


class LegacyConfigurationTests(unittest.TestCase):
    def test_empty_host_overrides_use_local_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {"OLLAMA_HOST": "", "OPENAI_BASE_URL": ""},
            clear=False,
        ):
            module = load_legacy_config()

        self.assertEqual(
            module.DEFAULT_OLLAMA_HOST, "http://localhost:11434"
        )
        self.assertEqual(
            module.DEFAULT_OPENAI_BASE_URL,
            "http://localhost:11434/v1",
        )

    def test_environment_override_is_preferred_and_expands_user(self) -> None:
        module = load_legacy_config()
        with patch.dict(
            os.environ,
            {"HEP_TEST_EXECUTABLE": "~/tools/bin/example"},
            clear=False,
        ):
            resolved = module.resolve_executable(
                environment_variable="HEP_TEST_EXECUTABLE",
                config_key="example_executable",
                candidates=("example",),
                config_path=Path("/does/not/exist"),
            )

        self.assertEqual(
            resolved,
            str(Path.home() / "tools" / "bin" / "example"),
        )

    def test_existing_local_paths_configuration_is_reused(self) -> None:
        module = load_legacy_config()
        with tempfile.TemporaryDirectory() as temporary:
            configured = Path(temporary) / "tools" / "example"
            config_path = Path(temporary) / "local_paths.json"
            config_path.write_text(
                json.dumps({"example_executable": str(configured)}),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                resolved = module.resolve_executable(
                    environment_variable="HEP_TEST_EXECUTABLE",
                    config_key="example_executable",
                    candidates=("example",),
                    config_path=config_path,
                )

        self.assertEqual(resolved, str(configured))

    def test_path_discovery_is_used_when_no_override_exists(self) -> None:
        module = load_legacy_config()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                module.shutil,
                "which",
                side_effect=lambda candidate: (
                    "/portable/bin/example" if candidate == "example" else None
                ),
            ),
        ):
            resolved = module.resolve_executable(
                environment_variable="HEP_TEST_EXECUTABLE",
                config_key="example_executable",
                candidates=("missing", "example"),
                config_path=Path("/does/not/exist"),
            )

        self.assertEqual(resolved, "/portable/bin/example")

    def test_command_name_remains_as_portable_path_fallback(self) -> None:
        module = load_legacy_config()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(module.shutil, "which", return_value=None),
        ):
            resolved = module.resolve_executable(
                environment_variable="HEP_TEST_EXECUTABLE",
                config_key="example_executable",
                candidates=("example",),
                config_path=Path("/does/not/exist"),
            )

        self.assertEqual(resolved, "example")

    def test_unresolved_ma5_command_does_not_derive_relative_path(self) -> None:
        module = load_legacy_bootstrap("ma5")
        with patch.object(module.shutil, "which", return_value=None):
            result = module.heal_environment()

        self.assertEqual(
            result,
            "⚠️ MadAnalysis5 executable not found. Skipping auto-repair.",
        )


if __name__ == "__main__":
    unittest.main()
