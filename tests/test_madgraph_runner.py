"""Tests for the safe MadGraph subprocess runner."""

import tempfile
import unittest
from pathlib import Path

from hep_agent.builders import (
    MadGraphArtifact,
    MadGraphWorkflowArtifact,
)
from hep_agent.execution import (
    ExecutionFailureCategory,
    run_madgraph_workflow,
)


def fake_artifact() -> MadGraphWorkflowArtifact:
    return MadGraphWorkflowArtifact(
        process_artifact=MadGraphArtifact(
            commands=(
                "import model sm",
                "generate p p > e+ e-",
                "output test_output",
            )
        ),
        launch_commands=(
            "launch test_output",
            "shower=OFF",
            "detector=OFF",
            "analysis=OFF",
            "set nevents 10",
            "set iseed 1",
            "set ebeam1 6500",
            "set ebeam2 6500",
            "done",
        ),
    )


def make_executable(
    directory: Path,
    name: str,
    body: str,
) -> Path:
    path = directory / name
    path.write_text(
        "#!/usr/bin/env python3\n" + body,
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


class MadGraphRunnerTests(unittest.TestCase):
    def test_manifest_free_execution_is_rejected_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = make_executable(root, "fake_mg5.py", "print(\"ran\")\n")
            result = run_madgraph_workflow(
                fake_artifact(),
                mg5_executable=executable,
                run_directory=root / "run",
                timeout_seconds=5,
            )
            self.assertFalse(result.success)
            self.assertEqual(
                result.failure_category,
                ExecutionFailureCategory.CONFIGURATION,
            )
            self.assertIn("explicit unsupported_nonhermetic", result.failure_message)

    def test_successful_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            executable = make_executable(
                root,
                "fake_mg5.py",
                (
                    "from pathlib import Path\n"
                    "import sys\n"
                    "text = Path(sys.argv[1]).read_text()\n"
                    "print('FAKE_MG5_OK')\n"
                    "print(text)\n"
                ),
            )

            result = run_madgraph_workflow(
                fake_artifact(),
                unsupported_nonhermetic=True,
                mg5_executable=executable,
                run_directory=root / "run",
                timeout_seconds=5,
            )

            self.assertTrue(result.success)
            self.assertEqual(result.returncode, 0)
            self.assertTrue(result.command_script_path.exists())
            self.assertIn(
                "FAKE_MG5_OK",
                result.stdout_path.read_text(
                    encoding="utf-8"
                ),
            )

    def test_nonzero_exit_is_classified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            executable = make_executable(
                root,
                "failing_mg5.py",
                (
                    "import sys\n"
                    "print('synthetic failure', file=sys.stderr)\n"
                    "raise SystemExit(7)\n"
                ),
            )

            result = run_madgraph_workflow(
                fake_artifact(),
                unsupported_nonhermetic=True,
                mg5_executable=executable,
                run_directory=root / "run",
                timeout_seconds=5,
            )

            self.assertFalse(result.success)
            self.assertEqual(result.returncode, 7)
            self.assertEqual(
                result.failure_category,
                ExecutionFailureCategory.NONZERO_EXIT,
            )

    def test_timeout_is_classified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            executable = make_executable(
                root,
                "slow_mg5.py",
                (
                    "import time\n"
                    "print('starting', flush=True)\n"
                    "time.sleep(2)\n"
                ),
            )

            result = run_madgraph_workflow(
                fake_artifact(),
                unsupported_nonhermetic=True,
                mg5_executable=executable,
                run_directory=root / "run",
                timeout_seconds=0.05,
            )

            self.assertFalse(result.success)
            self.assertEqual(
                result.failure_category,
                ExecutionFailureCategory.TIMEOUT,
            )

    def test_missing_executable_is_configuration_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_madgraph_workflow(
                fake_artifact(),
                unsupported_nonhermetic=True,
                mg5_executable=root / "missing_mg5",
                run_directory=root / "run",
                timeout_seconds=5,
            )

            self.assertFalse(result.success)
            self.assertEqual(
                result.failure_category,
                ExecutionFailureCategory.CONFIGURATION,
            )
            self.assertIsNone(result.returncode)


if __name__ == "__main__":
    unittest.main()
