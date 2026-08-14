"""Tests for the installer MA5 smoke-test command."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_madanalysis_runtime.py"


def make_fake_ma5(directory: Path, *, error: bool) -> Path:
    executable = directory / ("ma5-error" if error else "ma5-pass")
    lines = [
        "#!/bin/sh",
        "echo 'MA5 release : test'",
        "echo 'Checking the MadAnalysis 5 core library:'",
    ]
    if error:
        lines.append("echo 'MA5-ERROR: incompatible selected ROOT'")
    executable.write_text("\n".join(lines) + "\n", encoding="utf-8")
    executable.chmod(0o755)
    return executable


class ValidateMadAnalysisRuntimeTests(unittest.TestCase):
    def test_clean_existing_ma5_passes_smoke_test(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--ma5",
                    str(make_fake_ma5(root, error=False)),
                    "--output-directory",
                    str(root / "logs"),
                    "--attempt",
                    "reuse",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("smoke test passed", completed.stdout)

    def test_existing_ma5_with_real_error_fails_smoke_test(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--ma5",
                    str(make_fake_ma5(root, error=True)),
                    "--output-directory",
                    str(root / "logs"),
                    "--attempt",
                    "reuse",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 1)
            self.assertIn(
                "MA5-ERROR: incompatible selected ROOT",
                completed.stderr,
            )
            self.assertTrue((root / "logs" / "stdout-reuse.log").is_file())


if __name__ == "__main__":
    unittest.main()
