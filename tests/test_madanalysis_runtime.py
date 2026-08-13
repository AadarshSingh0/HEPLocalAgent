"""Tests for deterministic MadAnalysis runtime isolation."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from hep_agent.analysis.runtime import (
    MadAnalysisRuntimeConfigurationError,
    build_madanalysis_environment,
    load_madanalysis_runtime,
    runtime_metadata_path,
    verify_root_metadata,
)


def make_executable(path: Path, text: str = "#!/bin/sh\nexit 0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


class MadAnalysisRuntimeTests(unittest.TestCase):
    def test_unmanaged_runtime_removes_conflicting_shell_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = make_executable(Path(temporary) / "ma5")
            inherited = {
                "HOME": "/safe/home",
                "PATH": "/snap/bin:/opt/old-root/bin",
                "ROOTSYS": "/opt/old-root",
                "LD_LIBRARY_PATH": "/opt/old-root/lib",
                "PYTHONPATH": "/old/clone/.venv/lib",
                "VIRTUAL_ENV": "/old/clone/.venv",
                "CONDA_PREFIX": "/old/conda",
                "CONDA_DEFAULT_ENV": "base",
                "_CE_CONDA": "conda",
            }

            environment = build_madanalysis_environment(
                executable,
                inherited=inherited,
            )

            self.assertEqual(environment["HOME"], "/safe/home")
            self.assertEqual(
                environment["VIRTUAL_ENV"],
                str(Path(sys.executable).resolve().parent.parent),
            )
            for variable in (
                "ROOTSYS",
                "LD_LIBRARY_PATH",
                "PYTHONPATH",
                "CONDA_PREFIX",
                "CONDA_DEFAULT_ENV",
                "_CE_CONDA",
            ):
                self.assertNotIn(variable, environment)
            self.assertNotIn("/snap/bin", environment["PATH"])
            self.assertNotIn("/opt/old-root", environment["PATH"])

    def test_managed_runtime_replaces_root_and_conda_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            managed_root = root / "managed-root"
            root_bindir = managed_root / "bin"
            root_libdir = managed_root / "lib"
            root_libdir.mkdir(parents=True)
            python = Path(sys.executable).absolute()
            native_ma5 = make_executable(root / "tools/ma5/bin/ma5")
            launcher = make_executable(root / "tools/bin/hep-agent-ma5")
            root_config = make_executable(root_bindir / "root-config")

            runtime_metadata_path(launcher).write_text(
                json.dumps(
                    {
                        "platform": "Linux",
                        "python_executable": str(python),
                        "native_executable": str(native_ma5),
                        "root_config": str(root_config),
                        "root_prefix": str(managed_root),
                        "root_bindir": str(root_bindir),
                        "root_libdir": str(root_libdir),
                    }
                ),
                encoding="utf-8",
            )

            environment = build_madanalysis_environment(
                launcher,
                inherited={
                    "ROOTSYS": "/opt/root",
                    "LD_LIBRARY_PATH": "/opt/root/lib:/conda/lib",
                    "PATH": "/snap/bin:/conda/bin",
                    "PYTHONPATH": "/old/clone/.venv/lib",
                    "VIRTUAL_ENV": "/old/clone/.venv",
                    "CONDA_PREFIX": "/conda",
                },
            )

            self.assertEqual(environment["ROOTSYS"], str(managed_root))
            self.assertEqual(
                environment["LD_LIBRARY_PATH"],
                str(root_libdir),
            )
            self.assertEqual(
                environment["VIRTUAL_ENV"],
                str(python.parent.parent),
            )
            self.assertEqual(
                environment["PATH"].split(os.pathsep)[:2],
                [str(root_bindir), str(python.parent)],
            )
            self.assertNotIn("PYTHONPATH", environment)
            self.assertNotIn("CONDA_PREFIX", environment)

    def test_stale_previous_clone_python_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            managed_root = root / "root"
            (managed_root / "bin").mkdir(parents=True)
            (managed_root / "lib").mkdir()
            launcher = make_executable(root / "hep-agent-ma5")
            native_ma5 = make_executable(root / "ma5")
            root_config = make_executable(
                managed_root / "bin" / "root-config"
            )
            stale_python = make_executable(
                root / "previous-clone" / ".venv/bin/python"
            )

            runtime_metadata_path(launcher).write_text(
                json.dumps(
                    {
                        "platform": "Linux",
                        "python_executable": str(stale_python),
                        "native_executable": str(native_ma5),
                        "root_config": str(root_config),
                        "root_prefix": str(managed_root),
                        "root_bindir": str(managed_root / "bin"),
                        "root_libdir": str(managed_root / "lib"),
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                MadAnalysisRuntimeConfigurationError,
                "current clone",
            ):
                load_madanalysis_runtime(launcher)

    def test_root_metadata_must_still_match_root_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selected_root = root / "selected-root"
            unrelated_root = root / "opt-root"
            (selected_root / "bin").mkdir(parents=True)
            (selected_root / "lib").mkdir()
            unrelated_root.mkdir()
            python = Path(sys.executable).absolute()
            native_ma5 = make_executable(root / "tools/ma5")
            launcher = make_executable(root / "tools/hep-agent-ma5")
            root_config = make_executable(
                selected_root / "bin/root-config",
                (
                    "#!/bin/sh\n"
                    "case \"$1\" in\n"
                    f"  --prefix) echo {unrelated_root} ;;\n"
                    f"  --bindir) echo {selected_root / 'bin'} ;;\n"
                    f"  --libdir) echo {selected_root / 'lib'} ;;\n"
                    "esac\n"
                ),
            )
            runtime_metadata_path(launcher).write_text(
                json.dumps(
                    {
                        "platform": "Linux",
                        "python_executable": str(python),
                        "native_executable": str(native_ma5),
                        "root_config": str(root_config),
                        "root_prefix": str(selected_root),
                        "root_bindir": str(selected_root / "bin"),
                        "root_libdir": str(selected_root / "lib"),
                    }
                ),
                encoding="utf-8",
            )
            runtime = load_madanalysis_runtime(launcher)
            self.assertIsNotNone(runtime)

            with self.assertRaisesRegex(
                MadAnalysisRuntimeConfigurationError,
                "no longer matches",
            ):
                verify_root_metadata(runtime)


if __name__ == "__main__":
    unittest.main()
