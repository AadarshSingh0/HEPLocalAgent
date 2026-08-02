"""Tests for structured deterministic MA5 compilation."""

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from hep_agent.analysis.madanalysis import (
    MadAnalysisArtifact,
    MadAnalysisBuildError,
    MadAnalysisLevel,
    build_madanalysis_from_plan,
    build_madanalysis_quicklook,
    validate_madanalysis_artifact,
)
from hep_agent.schemas.analysis import (
    AnalysisComparison,
    AnalysisCutSpec,
    AnalysisHistogramSpec,
    AnalysisObjectRef,
    AnalysisObservable,
    AnalysisPlan,
)
from hep_agent.schemas.workflow import (
    WorkflowIntent,
)

from test_madanalysis_builder import (
    make_dilepton_workflow,
)


def make_structured_plan() -> AnalysisPlan:
    return AnalysisPlan(
        cuts=[
            AnalysisCutSpec(
                cut_id="electron_pt",
                observable=(
                    AnalysisObservable.PT
                ),
                objects=[
                    AnalysisObjectRef(
                        particle="e+",
                        rank=1,
                    )
                ],
                comparison=(
                    AnalysisComparison
                    .GREATER_THAN
                ),
                value=20,
            ),
            AnalysisCutSpec(
                cut_id="electron_eta",
                observable=(
                    AnalysisObservable.ABS_ETA
                ),
                objects=[
                    AnalysisObjectRef(
                        particle="e+",
                        rank=1,
                    )
                ],
                comparison=(
                    AnalysisComparison
                    .LESS_THAN
                ),
                value=2.5,
            ),
        ],
        histograms=[
            AnalysisHistogramSpec(
                histogram_id="dilepton_mass",
                observable=(
                    AnalysisObservable
                    .INVARIANT_MASS
                ),
                objects=[
                    AnalysisObjectRef(
                        particle="e+",
                        rank=1,
                    ),
                    AnalysisObjectRef(
                        particle="e-",
                        rank=1,
                    ),
                ],
                bins=30,
                minimum=60,
                maximum=120,
            ),
            AnalysisHistogramSpec(
                histogram_id="positron_pt",
                observable=(
                    AnalysisObservable.PT
                ),
                objects=[
                    AnalysisObjectRef(
                        particle="e+",
                        rank=1,
                    )
                ],
                bins=40,
                minimum=0,
                maximum=200,
            ),
        ],
    )


class StructuredMadAnalysisTests(
    unittest.TestCase
):
    def test_structured_plan_compiles_exact_commands(
        self,
    ) -> None:
        workflow = make_dilepton_workflow()
        plan = make_structured_plan()

        workflow.analysis = plan

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event_file = root / "events.hepmc.gz"
            event_file.write_bytes(b"fake")

            artifact = (
                build_madanalysis_from_plan(
                    workflow,
                    plan,
                    input_file=event_file,
                    job_directory=(
                        root / "structured_job"
                    ),
                    level=(
                        MadAnalysisLevel.HADRON
                    ),
                )
            )

        self.assertEqual(
            artifact.expected_cut_count,
            2,
        )
        self.assertEqual(
            artifact.expected_plot_count,
            2,
        )

        self.assertIn(
            "select PT(e+[1]) > 20",
            artifact.commands,
        )
        self.assertIn(
            "select ABSETA(e+[1]) < 2.5",
            artifact.commands,
        )
        self.assertIn(
            "plot M(e+[1] e-[1]) 30 60 120",
            artifact.commands,
        )
        self.assertIn(
            "plot PT(e+[1]) 40 0 200",
            artifact.commands,
        )

    def test_delta_observables_use_comma_syntax(
        self,
    ) -> None:
        workflow = make_dilepton_workflow()

        plan = AnalysisPlan(
            histograms=[
                AnalysisHistogramSpec(
                    histogram_id="delta_r",
                    observable=(
                        AnalysisObservable
                        .DELTA_R
                    ),
                    objects=[
                        AnalysisObjectRef(
                            particle="e+"
                        ),
                        AnalysisObjectRef(
                            particle="e-"
                        ),
                    ],
                    bins=40,
                    minimum=0,
                    maximum=6,
                )
            ]
        )

        workflow.analysis = plan

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event_file = root / "events.lhe.gz"
            event_file.write_bytes(b"fake")

            artifact = (
                build_madanalysis_from_plan(
                    workflow,
                    plan,
                    input_file=event_file,
                    job_directory=root / "job",
                    level=(
                        MadAnalysisLevel.PARTON
                    ),
                )
            )

        self.assertIn(
            "plot DELTAR(e+[1],e-[1]) 40 0 6",
            artifact.commands,
        )

    def test_particle_absent_from_workflow_is_blocked(
        self,
    ) -> None:
        workflow = make_dilepton_workflow()

        plan = AnalysisPlan(
            histograms=[
                AnalysisHistogramSpec(
                    histogram_id="muon_pt",
                    observable=(
                        AnalysisObservable.PT
                    ),
                    objects=[
                        AnalysisObjectRef(
                            particle="mu+"
                        )
                    ],
                    bins=40,
                    minimum=0,
                    maximum=200,
                )
            ]
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event_file = root / "events.lhe"
            event_file.write_bytes(b"fake")

            with self.assertRaises(
                MadAnalysisBuildError
            ):
                build_madanalysis_from_plan(
                    workflow,
                    plan,
                    input_file=event_file,
                    job_directory=root / "job",
                    level=(
                        MadAnalysisLevel.PARTON
                    ),
                )

    def test_wrong_object_count_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValidationError
        ):
            AnalysisHistogramSpec(
                histogram_id="bad_mass",
                observable=(
                    AnalysisObservable
                    .INVARIANT_MASS
                ),
                objects=[
                    AnalysisObjectRef(
                        particle="e+"
                    )
                ],
                bins=20,
                minimum=0,
                maximum=100,
            )

    def test_analysis_requires_madanalysis_pipeline(
        self,
    ) -> None:
        workflow = make_dilepton_workflow()

        payload = workflow.model_dump(
            mode="json"
        )
        payload["pipeline"][
            "madanalysis"
        ] = False
        payload["analysis"] = (
            make_structured_plan()
            .model_dump(mode="json")
        )

        with self.assertRaises(
            ValidationError
        ):
            WorkflowIntent.model_validate(
                payload
            )

    def test_cut_count_mismatch_is_rejected(
        self,
    ) -> None:
        workflow = make_dilepton_workflow()
        plan = make_structured_plan()
        workflow.analysis = plan

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event_file = root / "events.lhe"
            event_file.write_bytes(b"fake")

            original = (
                build_madanalysis_from_plan(
                    workflow,
                    plan,
                    input_file=event_file,
                    job_directory=root / "job",
                    level=(
                        MadAnalysisLevel.PARTON
                    ),
                )
            )

            modified = MadAnalysisArtifact(
                level=original.level,
                input_file=original.input_file,
                job_directory=(
                    original.job_directory
                ),
                commands=(
                    original.commands[0],
                    "select PT(e-[1]) > 999",
                    *original.commands[1:],
                ),
                expected_plot_count=(
                    original.expected_plot_count
                ),
                expected_cut_count=(
                    original.expected_cut_count
                ),
            )

            report = (
                validate_madanalysis_artifact(
                    modified
                )
            )

        self.assertFalse(
            report.is_valid
        )
        self.assertIn(
            "cut_count_mismatch",
            {
                issue.code
                for issue in report.issues
            },
        )

    def test_default_quicklook_remains_unchanged(
        self,
    ) -> None:
        workflow = make_dilepton_workflow()

        self.assertIsNone(
            workflow.analysis
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event_file = root / "events.hepmc.gz"
            event_file.write_bytes(b"fake")

            artifact = (
                build_madanalysis_quicklook(
                    workflow,
                    input_file=event_file,
                    job_directory=(
                        root / "quicklook_job"
                    ),
                    level=(
                        MadAnalysisLevel.HADRON
                    ),
                )
            )

        self.assertEqual(
            artifact.expected_plot_count,
            6,
        )
        self.assertEqual(
            artifact.expected_cut_count,
            0,
        )


if __name__ == "__main__":
    unittest.main()
