"""End-to-end tests including separate MA5 post-processing."""

import json
import tempfile
import unittest
from pathlib import Path

from hep_agent.models import AgentProfile, ModelResponse
from hep_agent.orchestration import (
    EndToEndStatus,
    run_end_to_end,
)


REQUEST = (
    "Simulate proton-proton collisions producing an electron and a "
    "positron at 13 TeV. Generate 10 events and create default plots."
)


def planner_payload() -> dict:
    return {
        "schema_version": "1.0",
        "task_type": "run_simulation",
        "model": {
            "name": "sm",
            "source": "builtin",
            "model_path": None,
        },
        "collider": {
            "collider_type": "hadron",
            "beams": [
                {"particle": "p"},
                {"particle": "p"},
            ],
            "energy": {
                "value_gev": 13000,
                "meaning": "total_center_of_mass",
            },
        },
        "processes": [
            {
                "process_id": "dilepton",
                "incoming_particles": ["p", "p"],
                "final_particles": [
                    {
                        "particle": "e+",
                        "decay_products": [],
                    },
                    {
                        "particle": "e-",
                        "decay_products": [],
                    },
                ],
                "required_intermediates": [],
                "excluded_particles": [],
                "coupling_orders": {},
            }
        ],
        "run": {
            "nevents": 10,
            "random_seed": 1,
            "timeout_seconds": 30,
            "output_name": "test_process",
        },
        "pipeline": {
            "madgraph": True,
            "pythia8": False,
            "delphes": False,
            "madanalysis": True,
        },
        "field_sources": {},
        "notes": [],
    }


class FakeClient:
    def chat(self, **kwargs):
        return ModelResponse(
            model=kwargs["model"],
            content=json.dumps(planner_payload()),
            total_duration_ns=1_000_000_000,
        )


def make_fake_mg5(
    root: Path,
    *,
    write_lhe: bool = True,
) -> Path:
    path = root / "fake_mg5.py"

    path.write_text(
        f'''#!/usr/bin/env python3
from pathlib import Path

run_root = Path.cwd()
lhe = (
    run_root
    / "test_process"
    / "Events"
    / "run_01"
    / "unweighted_events.lhe.gz"
)
lhe.parent.mkdir(parents=True, exist_ok=True)

if {write_lhe!r}:
    lhe.write_bytes(b"fake")

print("Cross-section : 12.5 +- 0.5 pb")
print("Nb of events : 10")
''',
        encoding="utf-8",
    )
    path.chmod(0o755)

    return path


def make_fake_ma5(
    root: Path,
    *,
    internal_error: bool = False,
) -> Path:
    path = root / "fake_ma5.py"

    if internal_error:
        body = '''#!/usr/bin/env python3
print("MA5-ERROR: synthetic analysis failure")
'''
    else:
        body = '''#!/usr/bin/env python3
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
'''

    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)

    return path


class EndToEndMadAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = AgentProfile(
            primary_model="qwen",
            primary_timeout_seconds=30,
            max_repairs=1,
        )

    def test_complete_run_records_ma5_reports(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_end_to_end(
                REQUEST,
                client=FakeClient(),
                profile_name="test",
                profile=self.profile,
                mg5_executable=make_fake_mg5(root),
                madanalysis_executable=make_fake_ma5(root),
                approval_resolver=lambda approval: True,
                records_directory=root / "records",
                executions_directory=root / "executions",
                analyses_directory=root / "analyses",
                project_root=root,
            )

            record = result.final_record

            self.assertEqual(
                result.status,
                EndToEndStatus.COMPLETED,
            )
            self.assertTrue(result.success)
            self.assertTrue(record.execution_success)
            self.assertTrue(record.analysis_requested)
            self.assertTrue(record.analysis_started)
            self.assertTrue(record.analysis_success)
            self.assertEqual(
                record.analysis_level,
                "parton",
            )
            self.assertEqual(
                len(record.analysis_plot_files),
                6,
            )
            self.assertIsNotNone(
                record.analysis_html_report
            )
            self.assertIsNotNone(
                record.analysis_pdf_report
            )
            self.assertNotIn(
                str(root),
                record.analysis_html_report,
            )

    def test_ma5_failure_preserves_mg5_success(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_end_to_end(
                REQUEST,
                client=FakeClient(),
                profile_name="test",
                profile=self.profile,
                mg5_executable=make_fake_mg5(root),
                madanalysis_executable=make_fake_ma5(
                    root,
                    internal_error=True,
                ),
                approval_resolver=lambda approval: True,
                records_directory=root / "records",
                executions_directory=root / "executions",
                analyses_directory=root / "analyses",
                project_root=root,
            )

            record = result.final_record

            self.assertEqual(
                result.status,
                EndToEndStatus.ANALYSIS_FAILED,
            )
            self.assertFalse(result.success)
            self.assertTrue(record.execution_success)
            self.assertFalse(record.analysis_success)
            self.assertEqual(
                record.analysis_failure_category,
                "analysis_execution_failure",
            )
            self.assertEqual(
                record.final_status,
                "analysis_failed",
            )

    def test_missing_event_output_records_unstarted_ma5(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_end_to_end(
                REQUEST,
                client=FakeClient(),
                profile_name="test",
                profile=self.profile,
                mg5_executable=make_fake_mg5(
                    root,
                    write_lhe=False,
                ),
                madanalysis_executable=make_fake_ma5(root),
                approval_resolver=lambda approval: True,
                records_directory=root / "records",
                executions_directory=root / "executions",
                analyses_directory=root / "analyses",
                project_root=root,
            )

            record = result.final_record

            self.assertEqual(
                result.status,
                EndToEndStatus.EXECUTION_FAILED,
            )
            self.assertTrue(record.analysis_requested)
            self.assertFalse(record.analysis_started)
            self.assertIsNone(record.analysis_success)


if __name__ == "__main__":
    unittest.main()
