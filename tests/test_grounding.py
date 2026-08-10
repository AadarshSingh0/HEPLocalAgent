"""Tests for grounding planner output in explicit user facts."""

import unittest

from hep_agent.schemas import (
    BeamSpec,
    ColliderSpec,
    ColliderType,
    EnergyMeaning,
    EnergySpec,
    FieldSource,
    ParticleNode,
    PhysicsModelSpec,
    PipelineSpec,
    ProcessSpec,
    RunSettings,
    TaskType,
    WorkflowIntent,
)
from hep_agent.validation import (
    extract_explicit_request_facts,
    validate_request_grounding,
)


REQUEST = (
    "Simulate proton-proton collisions producing an electron and a "
    "positron at a total centre-of-mass energy of 13 TeV. "
    "Generate 10000 events. Do not use Pythia8 or Delphes."
)


MULTILINE_ANALYSIS_REQUEST = """
Simulate proton-proton collisions producing an electron and a
positron at 13 TeV. Generate 200 events with Pythia8. Do not
use Delphes.

Use MadAnalysis to plot the electron-positron invariant mass
from 60 to 120 GeV with 30 bins. Require both particles to
have transverse momentum greater than 20 GeV and absolute
pseudorapidity less than 2.5.
"""


def make_workflow(
    *,
    incoming: tuple[str, str] = ("p", "p"),
    final: tuple[str, str] = ("e-", "e+"),
    energy_gev: float = 13_000,
    nevents: int = 10_000,
    pythia8: bool = False,
    delphes: bool = False,
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
                value_gev=energy_gev,
                meaning=EnergyMeaning.TOTAL_CENTER_OF_MASS,
            ),
        ),
        processes=[
            ProcessSpec(
                incoming_particles=list(incoming),
                final_particles=[
                    ParticleNode(particle=final[0]),
                    ParticleNode(particle=final[1]),
                ],
            )
        ],
        run=RunSettings(nevents=nevents),
        pipeline=PipelineSpec(
            madgraph=True,
            pythia8=pythia8,
            delphes=delphes,
        ),
        field_sources={
            "model.name": FieldSource.MODEL_INFERENCE,
            "collider.beams": FieldSource.MODEL_INFERENCE,
            "collider.energy.value_gev": FieldSource.MODEL_INFERENCE,
            "processes": FieldSource.MODEL_INFERENCE,
        },
    )


class GroundingTests(unittest.TestCase):
    def test_mixed_four_lepton_state_preserves_every_particle(
        self,
    ) -> None:
        facts = extract_explicit_request_facts(
            "Simulate proton-proton collisions producing a muon, "
            "an antimuon, an electron, and a positron at 13 TeV "
            "with 100 events."
        )

        self.assertEqual(
            facts.final_particles,
            ("mu-", "mu+", "e-", "e+"),
        )

    def test_charge_qualified_muon_is_not_duplicated(
        self,
    ) -> None:
        facts = extract_explicit_request_facts(
            "Simulate proton-proton collisions producing a positive "
            "muon and a Higgs boson at 13 TeV with 100 events."
        )

        self.assertEqual(
            facts.final_particles,
            ("mu+", "h"),
        )

    def test_hyphenated_antitop_is_not_also_counted_as_top(
        self,
    ) -> None:
        facts = extract_explicit_request_facts(
            "Simulate proton-proton collisions producing an anti-top "
            "quark and a Higgs boson at 13 TeV with 100 events."
        )

        self.assertEqual(
            facts.final_particles,
            ("t~", "h"),
        )

    def test_multiline_analysis_facts_are_extracted(
        self,
    ) -> None:
        facts = extract_explicit_request_facts(
            MULTILINE_ANALYSIS_REQUEST
        )

        self.assertEqual(
            facts.collider_beams,
            ("p", "p"),
        )
        self.assertEqual(
            facts.final_particles,
            ("e-", "e+"),
        )
        self.assertEqual(
            facts.energy_gev,
            13_000,
        )
        self.assertEqual(
            facts.nevents,
            200,
        )
        self.assertTrue(
            facts.pythia8
        )
        self.assertFalse(
            facts.delphes
        )

    def test_multiline_analysis_request_is_grounded(
        self,
    ) -> None:
        request = """
        Simulate proton-proton collisions producing an electron and a
        positron at 13 TeV. Generate 200 events with Pythia8. Do not
        use Delphes.

        Use MadAnalysis to plot the electron-positron invariant mass
        from 60 to 120 GeV with 30 bins. Require both particles to
        have transverse momentum greater than 20 GeV and absolute
        pseudorapidity less than 2.5.
        """

        payload = make_workflow(
            nevents=200,
            pythia8=True,
            delphes=False,
        ).model_dump(
            mode="json"
        )

        payload["pipeline"][
            "madanalysis"
        ] = True

        payload["analysis"] = {
            "schema_version": "1.0",
            "histograms": [
                {
                    "histogram_id": "ee_mass",
                    "observable": "invariant_mass",
                    "objects": [
                        {
                            "particle": "e+",
                            "rank": 1
                        },
                        {
                            "particle": "e-",
                            "rank": 1
                        }
                    ],
                    "unit": "GeV",
                    "bins": 30,
                    "minimum": 60.0,
                    "maximum": 120.0
                }
            ],
            "cuts": [
                {
                    "cut_id": "positron_pt",
                    "observable": "pt",
                    "objects": [
                        {
                            "particle": "e+",
                            "rank": 1
                        }
                    ],
                    "unit": "GeV",
                    "comparison": ">",
                    "value": 20.0
                },
                {
                    "cut_id": "electron_pt",
                    "observable": "pt",
                    "objects": [
                        {
                            "particle": "e-",
                            "rank": 1
                        }
                    ],
                    "unit": "GeV",
                    "comparison": ">",
                    "value": 20.0
                },
                {
                    "cut_id": "positron_abs_eta",
                    "observable": "abs_eta",
                    "objects": [
                        {
                            "particle": "e+",
                            "rank": 1
                        }
                    ],
                    "unit": "dimensionless",
                    "comparison": "<",
                    "value": 2.5
                },
                {
                    "cut_id": "electron_abs_eta",
                    "observable": "abs_eta",
                    "objects": [
                        {
                            "particle": "e-",
                            "rank": 1
                        }
                    ],
                    "unit": "dimensionless",
                    "comparison": "<",
                    "value": 2.5
                }
            ]
        }

        workflow = WorkflowIntent.model_validate(
            payload
        )

        result = validate_request_grounding(
            request,
            workflow,
        )

        self.assertTrue(
            result.report.is_valid,
            result.report.issues,
        )


    def test_stage_negation_is_scoped_to_target(
        self,
    ) -> None:
        request = (
            "Simulate proton-proton collisions producing an "
            "electron and a positron at 13 TeV. Generate 100 "
            "events with Pythia8 and no Delphes."
        )

        facts = extract_explicit_request_facts(
            request
        )

        self.assertTrue(
            facts.pythia8
        )
        self.assertFalse(
            facts.delphes
        )

    def test_exact_request_is_grounded(self) -> None:
        result = validate_request_grounding(
            REQUEST,
            make_workflow(),
        )

        self.assertTrue(result.report.is_valid)

    def test_partonic_substitution_is_rejected(self) -> None:
        result = validate_request_grounding(
            REQUEST,
            make_workflow(incoming=("q", "q~")),
        )

        self.assertFalse(result.report.is_valid)
        self.assertIn(
            "explicit_process_incoming_mismatch",
            [issue.code for issue in result.report.errors],
        )

    def test_final_state_change_is_rejected(self) -> None:
        result = validate_request_grounding(
            REQUEST,
            make_workflow(final=("mu-", "mu+")),
        )

        self.assertFalse(result.report.is_valid)
        self.assertIn(
            "explicit_final_state_mismatch",
            [issue.code for issue in result.report.errors],
        )

    def test_energy_change_is_rejected(self) -> None:
        result = validate_request_grounding(
            REQUEST,
            make_workflow(energy_gev=14_000),
        )

        self.assertFalse(result.report.is_valid)
        self.assertIn(
            "explicit_energy_mismatch",
            [issue.code for issue in result.report.errors],
        )

    def test_pipeline_change_is_rejected(self) -> None:
        result = validate_request_grounding(
            REQUEST,
            make_workflow(pythia8=True),
        )

        self.assertFalse(result.report.is_valid)
        self.assertIn(
            "explicit_pythia_choice_mismatch",
            [issue.code for issue in result.report.errors],
        )

    def test_explicit_provenance_is_corrected(self) -> None:
        result = validate_request_grounding(
            REQUEST,
            make_workflow(),
        )

        sources = result.workflow.field_sources

        self.assertEqual(
            sources["collider.beams"],
            FieldSource.USER,
        )
        self.assertEqual(
            sources["collider.energy.value_gev"],
            FieldSource.USER,
        )
        self.assertEqual(
            sources["processes"],
            FieldSource.USER,
        )
        self.assertEqual(
            sources["run.nevents"],
            FieldSource.USER,
        )
        self.assertEqual(
            sources["pipeline.pythia8"],
            FieldSource.USER,
        )
        self.assertEqual(
            sources["pipeline.delphes"],
            FieldSource.USER,
        )
        self.assertEqual(
            sources["model.name"],
            FieldSource.VALIDATED_DEFAULT,
        )


if __name__ == "__main__":
    unittest.main()
