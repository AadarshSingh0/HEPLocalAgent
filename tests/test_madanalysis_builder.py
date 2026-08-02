"""Tests for deterministic MadAnalysis script construction."""

import tempfile
import unittest
from pathlib import Path

from hep_agent.analysis import (
    MadAnalysisArtifact,
    MadAnalysisBuildError,
    MadAnalysisLevel,
    build_madanalysis_quicklook,
    validate_madanalysis_artifact,
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


def make_dilepton_workflow() -> WorkflowIntent:
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
            nevents=100,
            output_name="dilepton",
        ),
        pipeline=PipelineSpec(
            madgraph=True,
            pythia8=True,
            delphes=False,
            madanalysis=True,
        ),
    )


class MadAnalysisBuilderTests(unittest.TestCase):
    def test_dilepton_quicklook_has_six_plots(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event_file = root / "events.hepmc.gz"
            event_file.write_bytes(b"fake")

            artifact = build_madanalysis_quicklook(
                make_dilepton_workflow(),
                input_file=event_file,
                job_directory=root / "quicklook_job",
                level=MadAnalysisLevel.HADRON,
            )

            self.assertEqual(
                artifact.expected_plot_count,
                6,
            )
            self.assertEqual(
                artifact.mode_flag,
                "-H",
            )
            self.assertIn(
                "plot PT(e+[1]) 40 0 400",
                artifact.commands,
            )
            self.assertIn(
                "plot PT(e-[1]) 40 0 400",
                artifact.commands,
            )
            self.assertIn(
                "plot M(e+ e-) 50 0 500",
                artifact.commands,
            )
            self.assertIn(
                "plot MET 40 0 400",
                artifact.commands,
            )

    def test_script_imports_and_submits_absolute_paths(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event_file = root / "events.hepmc.gz"
            event_file.write_bytes(b"fake")
            job_directory = root / "job"

            artifact = build_madanalysis_quicklook(
                make_dilepton_workflow(),
                input_file=event_file,
                job_directory=job_directory,
                level=MadAnalysisLevel.HADRON,
            )

            self.assertEqual(
                artifact.commands[0],
                f"import {event_file.resolve()} as sample",
            )
            self.assertEqual(
                artifact.commands[-2],
                f"submit {job_directory.resolve()}",
            )
            self.assertEqual(
                artifact.commands[-1],
                "quit",
            )

    def test_valid_artifact_passes_validation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event_file = root / "events.hepmc.gz"
            event_file.write_bytes(b"fake")

            artifact = build_madanalysis_quicklook(
                make_dilepton_workflow(),
                input_file=event_file,
                job_directory=root / "job",
                level=MadAnalysisLevel.HADRON,
            )

            report = validate_madanalysis_artifact(
                artifact
            )

            self.assertTrue(report.is_valid)
            self.assertEqual(report.issues, ())

    def test_modified_script_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event_file = root / "events.hepmc.gz"
            event_file.write_bytes(b"fake")

            original = build_madanalysis_quicklook(
                make_dilepton_workflow(),
                input_file=event_file,
                job_directory=root / "job",
                level=MadAnalysisLevel.HADRON,
            )

            modified = MadAnalysisArtifact(
                level=original.level,
                input_file=original.input_file,
                job_directory=original.job_directory,
                commands=(
                    *original.commands[:-1],
                    "shell rm -rf /",
                    "quit",
                ),
                expected_plot_count=(
                    original.expected_plot_count
                ),
            )

            report = validate_madanalysis_artifact(
                modified
            )

            self.assertFalse(report.is_valid)
            self.assertIn(
                "unsupported_command",
                {
                    issue.code
                    for issue in report.issues
                },
            )

    def test_unsupported_final_state_is_blocked(
        self,
    ) -> None:
        workflow = make_dilepton_workflow()
        workflow.processes[0].final_particles = [
            ParticleNode(particle="x1"),
            ParticleNode(particle="x1"),
        ]

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event_file = root / "events.hepmc.gz"
            event_file.write_bytes(b"fake")

            with self.assertRaises(
                MadAnalysisBuildError
            ):
                build_madanalysis_quicklook(
                    workflow,
                    input_file=event_file,
                    job_directory=root / "job",
                    level=MadAnalysisLevel.HADRON,
                )


if __name__ == "__main__":
    unittest.main()
