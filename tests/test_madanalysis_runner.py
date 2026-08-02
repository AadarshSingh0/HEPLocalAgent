"""Tests for the safe MadAnalysis subprocess runner."""

import tempfile
import unittest
from pathlib import Path

from hep_agent.analysis import (
    MadAnalysisFailureCategory,
    MadAnalysisLevel,
    build_madanalysis_quicklook,
    run_madanalysis_artifact,
)
from hep_agent.schemas import (
    BeamSpec,
    ColliderSpec,
    ColliderType,
    EnergyMeaning,
    EnergySpec,
    ParticleNode,
    PhysicsModelSpec,
    PipelineSpec,
    ProcessSpec,
    RunSettings,
    TaskType,
    WorkflowIntent,
)


def make_workflow() -> WorkflowIntent:
    return WorkflowIntent(
        task_type=TaskType.RUN_SIMULATION,
        model=PhysicsModelSpec(name="sm"),
        collider=ColliderSpec(
            collider_type=ColliderType.HADRON,
            beams=[
                BeamSpec(particle="p"),
                BeamSpec(particle="p"),
            ],
            energy=EnergySpec(
                value_gev=13_000,
                meaning=EnergyMeaning.TOTAL_CENTER_OF_MASS,
            ),
        ),
        processes=[
            ProcessSpec(
                process_id="dilepton",
                incoming_particles=["p", "p"],
                final_particles=[
                    ParticleNode(particle="e+"),
                    ParticleNode(particle="e-"),
                ],
            )
        ],
        run=RunSettings(
            nevents=10,
            output_name="dilepton",
        ),
        pipeline=PipelineSpec(
            madgraph=True,
            pythia8=True,
            delphes=False,
            madanalysis=True,
        ),
    )


def make_executable(
    directory: Path,
    *,
    mode: str,
) -> Path:
    path = directory / f"fake_ma5_{mode}.py"

    body = f'''#!/usr/bin/env python3
from pathlib import Path
import sys
import time

mode = {mode!r}
script = Path(sys.argv[-1])
text = script.read_text(encoding="utf-8")

submit_line = next(
    line for line in text.splitlines()
    if line.startswith("submit ")
)
job = Path(submit_line.removeprefix("submit "))

if mode == "timeout":
    time.sleep(2)

if mode == "nonzero":
    print("synthetic failure")
    raise SystemExit(7)

if mode == "internal_error":
    print("MA5-ERROR: synthetic script error")
    raise SystemExit(0)

if mode != "missing_reports":
    html = (
        job
        / "Output"
        / "HTML"
        / "MadAnalysis5job_0"
    )
    pdf = (
        job
        / "Output"
        / "PDF"
        / "MadAnalysis5job_0"
    )

    html.mkdir(parents=True, exist_ok=True)
    pdf.mkdir(parents=True, exist_ok=True)

    (html / "index.html").write_text(
        "<html></html>",
        encoding="utf-8",
    )
    (pdf / "main.pdf").write_bytes(b"pdf")

    plot_count = 5 if mode == "plot_mismatch" else 6

    for index in range(plot_count):
        (html / f"selection_{{index}}.png").write_bytes(
            b"png"
        )

print("MA5 synthetic execution complete")
'''

    path.write_text(
        body,
        encoding="utf-8",
    )
    path.chmod(0o755)

    return path


def make_artifact(root: Path):
    event_file = root / "events.hepmc.gz"
    event_file.write_bytes(b"fake")

    return build_madanalysis_quicklook(
        make_workflow(),
        input_file=event_file,
        job_directory=root / "quicklook_job",
        level=MadAnalysisLevel.HADRON,
    )


class MadAnalysisRunnerTests(unittest.TestCase):
    def test_success_requires_reports_and_plots(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_madanalysis_artifact(
                make_artifact(root),
                madanalysis_executable=(
                    make_executable(
                        root,
                        mode="success",
                    )
                ),
                analysis_directory=root / "analysis",
                timeout_seconds=5,
            )

            self.assertTrue(result.success)
            self.assertEqual(result.returncode, 0)
            self.assertIsNotNone(result.html_report)
            self.assertIsNotNone(result.pdf_report)
            self.assertEqual(
                len(result.plot_files),
                6,
            )

    def test_internal_error_fails_with_exit_zero(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_madanalysis_artifact(
                make_artifact(root),
                madanalysis_executable=(
                    make_executable(
                        root,
                        mode="internal_error",
                    )
                ),
                analysis_directory=root / "analysis",
                timeout_seconds=5,
            )

            self.assertFalse(result.success)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(
                result.failure_category,
                MadAnalysisFailureCategory
                .INTERNAL_ERROR,
            )
            self.assertEqual(
                len(result.internal_error_lines),
                1,
            )

    def test_nonzero_exit_is_classified(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_madanalysis_artifact(
                make_artifact(root),
                madanalysis_executable=(
                    make_executable(
                        root,
                        mode="nonzero",
                    )
                ),
                analysis_directory=root / "analysis",
                timeout_seconds=5,
            )

            self.assertFalse(result.success)
            self.assertEqual(result.returncode, 7)
            self.assertEqual(
                result.failure_category,
                MadAnalysisFailureCategory
                .NONZERO_EXIT,
            )

    def test_missing_reports_are_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_madanalysis_artifact(
                make_artifact(root),
                madanalysis_executable=(
                    make_executable(
                        root,
                        mode="missing_reports",
                    )
                ),
                analysis_directory=root / "analysis",
                timeout_seconds=5,
            )

            self.assertFalse(result.success)
            self.assertEqual(
                result.failure_category,
                MadAnalysisFailureCategory
                .MISSING_REPORT,
            )

    def test_plot_count_mismatch_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_madanalysis_artifact(
                make_artifact(root),
                madanalysis_executable=(
                    make_executable(
                        root,
                        mode="plot_mismatch",
                    )
                ),
                analysis_directory=root / "analysis",
                timeout_seconds=5,
            )

            self.assertFalse(result.success)
            self.assertEqual(
                result.failure_category,
                MadAnalysisFailureCategory
                .PLOT_COUNT_MISMATCH,
            )
            self.assertEqual(
                len(result.plot_files),
                5,
            )

    def test_timeout_is_classified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_madanalysis_artifact(
                make_artifact(root),
                madanalysis_executable=(
                    make_executable(
                        root,
                        mode="timeout",
                    )
                ),
                analysis_directory=root / "analysis",
                timeout_seconds=0.05,
            )

            self.assertFalse(result.success)
            self.assertEqual(
                result.failure_category,
                MadAnalysisFailureCategory.TIMEOUT,
            )

    def test_missing_executable_is_configuration_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_madanalysis_artifact(
                make_artifact(root),
                madanalysis_executable=(
                    root / "missing_ma5"
                ),
                analysis_directory=root / "analysis",
                timeout_seconds=5,
            )

            self.assertFalse(result.success)
            self.assertEqual(
                result.failure_category,
                MadAnalysisFailureCategory
                .CONFIGURATION,
            )


if __name__ == "__main__":
    unittest.main()
