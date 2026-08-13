"""Tests for separate MadAnalysis post-processing orchestration."""

import tempfile
import unittest
from pathlib import Path

from hep_agent.execution import MadGraphPhysicsResult
from hep_agent.orchestration import (
    AnalysisStageFailureCategory,
    run_madanalysis_stage,
    select_madanalysis_input,
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


def make_workflow(
    *,
    madanalysis: bool = True,
) -> WorkflowIntent:
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
                meaning=(
                    EnergyMeaning.TOTAL_CENTER_OF_MASS
                ),
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
            madanalysis=madanalysis,
        ),
    )


def make_physics(
    *,
    lhe: Path | None,
    hepmc: Path | None,
    root: Path | None = None,
) -> MadGraphPhysicsResult:
    return MadGraphPhysicsResult(
        cross_section_pb=10.0,
        cross_section_uncertainty_pb=0.2,
        event_count=10,
        primary_lhe_file=lhe,
        showered_hepmc_file=hepmc,
        detector_root_file=root,
        warnings=(),
    )


def make_fake_ma5(root: Path) -> Path:
    path = root / "fake_ma5.py"

    path.write_text(
        '''#!/usr/bin/env python3
from pathlib import Path
import sys

script = Path(sys.argv[-1])
text = script.read_text(encoding="utf-8")

submit = next(
    line.removeprefix("submit ")
    for line in text.splitlines()
    if line.startswith("submit ")
)

job = Path(submit)
html = job / "Output" / "HTML" / "MadAnalysis5job_0"
pdf = job / "Output" / "PDF" / "MadAnalysis5job_0"

html.mkdir(parents=True, exist_ok=True)
pdf.mkdir(parents=True, exist_ok=True)

(html / "index.html").write_text(
    "<html></html>",
    encoding="utf-8",
)
(pdf / "main.pdf").write_bytes(b"pdf")

for index in range(6):
    (html / f"selection_{index}.png").write_bytes(b"png")

print("Synthetic MA5 success")
''',
        encoding="utf-8",
    )
    path.chmod(0o755)

    return path


class AnalysisStageTests(unittest.TestCase):
    def test_delphes_root_is_preferred_over_hepmc_and_lhe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            lhe = directory / "events.lhe.gz"
            hepmc = directory / "events.hepmc.gz"
            root = directory / "events.root"
            for path in (lhe, hepmc, root):
                path.write_bytes(b"events")

            selection = select_madanalysis_input(
                make_physics(lhe=lhe, hepmc=hepmc, root=root)
            )

            self.assertIsNotNone(selection)
            self.assertEqual(selection.input_file, root)
            self.assertEqual(selection.level.value, "reconstructed")

    def test_hepmc_is_preferred_over_lhe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            lhe = root / "events.lhe.gz"
            hepmc = root / "events.hepmc.gz"

            lhe.write_bytes(b"lhe")
            hepmc.write_bytes(b"hepmc")

            selection = select_madanalysis_input(
                make_physics(
                    lhe=lhe,
                    hepmc=hepmc,
                )
            )

            self.assertIsNotNone(selection)
            self.assertEqual(
                selection.input_file,
                hepmc,
            )
            self.assertEqual(
                selection.level.value,
                "hadron",
            )

    def test_lhe_is_used_when_hepmc_is_absent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lhe = root / "events.lhe.gz"
            lhe.write_bytes(b"lhe")

            selection = select_madanalysis_input(
                make_physics(
                    lhe=lhe,
                    hepmc=None,
                )
            )

            self.assertIsNotNone(selection)
            self.assertEqual(
                selection.input_file,
                lhe,
            )
            self.assertEqual(
                selection.level.value,
                "parton",
            )

    def test_unrequested_analysis_is_skipped(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_madanalysis_stage(
                make_workflow(
                    madanalysis=False
                ),
                make_physics(
                    lhe=None,
                    hepmc=None,
                ),
                madanalysis_executable=None,
                analysis_directory=root,
            )

            self.assertFalse(result.requested)
            self.assertTrue(result.success)
            self.assertIsNone(result.execution)

    def test_missing_event_file_is_classified(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = run_madanalysis_stage(
                make_workflow(),
                make_physics(
                    lhe=None,
                    hepmc=None,
                ),
                madanalysis_executable=None,
                analysis_directory=temporary,
            )

            self.assertFalse(result.success)
            self.assertEqual(
                result.failure_category,
                AnalysisStageFailureCategory
                .INPUT_SELECTION,
            )

    def test_missing_executable_is_classified(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hepmc = root / "events.hepmc.gz"
            hepmc.write_bytes(b"hepmc")

            result = run_madanalysis_stage(
                make_workflow(),
                make_physics(
                    lhe=None,
                    hepmc=hepmc,
                ),
                madanalysis_executable=None,
                analysis_directory=root / "analysis",
            )

            self.assertFalse(result.success)
            self.assertEqual(
                result.failure_category,
                AnalysisStageFailureCategory
                .CONFIGURATION,
            )

    def test_successful_hadron_analysis(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hepmc = root / "events.hepmc.gz"
            hepmc.write_bytes(b"hepmc")

            result = run_madanalysis_stage(
                make_workflow(),
                make_physics(
                    lhe=None,
                    hepmc=hepmc,
                ),
                madanalysis_executable=(
                    make_fake_ma5(root)
                ),
                analysis_directory=root / "analysis",
            )

            self.assertTrue(result.requested)
            self.assertTrue(result.success)
            self.assertIsNotNone(result.execution)
            self.assertEqual(
                len(result.execution.plot_files),
                6,
            )


if __name__ == "__main__":
    unittest.main()
