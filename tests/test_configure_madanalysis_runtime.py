"""Tests for persistent MadAnalysis runtime configuration."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/configure_madanalysis_runtime.py"


def make_file(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class ConfigureMadAnalysisRuntimeTests(unittest.TestCase):
    def test_stale_clone_and_root_paths_are_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ma5_root = root / "tools/madanalysis5"
            ma5 = make_file(ma5_root / "bin/ma5")
            options = make_file(
                ma5_root / "madanalysis/input/installation_options.dat",
                (
                    "root_bin_path = /usr/bin\n"
                    "# delphes_veto = 0\n"
                    "delphes_includes = /old/clone/Delphes\n"
                    "delphes_libs = /old/clone/Delphes\n"
                ),
            )
            root_bindir = root / "selected-root/bin"
            make_file(root_bindir / "root-config")
            delphes = root / "managed/Delphes"
            make_file(delphes / "modules/ParticlePropagator.h")
            make_file(delphes / "libDelphes.so")

            command = [
                sys.executable,
                str(SCRIPT),
                "--ma5",
                str(ma5),
                "--root-bindir",
                str(root_bindir),
                "--delphes-root",
                str(delphes),
            ]
            first = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            second = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(first.returncode, 0, first.stdout)
            self.assertEqual(second.returncode, 0, second.stdout)
            self.assertIn("Updated", first.stdout)
            self.assertIn("Verified", second.stdout)
            configured = options.read_text(encoding="utf-8")
            self.assertIn(f"root_bin_path = {root_bindir.resolve()}", configured)
            self.assertIn(f"delphes_includes = {delphes.resolve()}", configured)
            self.assertIn(f"delphes_libs = {delphes.resolve()}", configured)
            self.assertNotIn("/old/clone", configured)
            self.assertNotIn("/usr/bin", configured)
            self.assertTrue(
                options.with_name(
                    options.name + ".before_hep_agent"
                ).is_file()
            )


if __name__ == "__main__":
    unittest.main()
