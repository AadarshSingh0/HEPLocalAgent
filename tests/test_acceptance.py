"""Data-driven acceptance harness.

Each scenario in ``tests/acceptance/scenarios.json`` describes a request, the
model output(s) to replay, and the expected outcome. Scenarios run through the
*real* pipeline - the full pre-execution loop for the ``full`` route, and the
semantic planner plus compiler for the ``semantic`` route - with a fake client
that replays the recorded outputs. This gives a paraphrase battery (many
phrasings -> same workflow) and a negative battery (invalid tokens are repaired
or blocked, never executed) that is refactor-proof.

The committed scenarios use representative model outputs so the suite is green
in CI without a running model. To validate real local-model behaviour, record
actual outputs with ``scripts/record_acceptance.py`` and point this harness at
the recorded file via the ``HEP_ACCEPTANCE_SCENARIOS`` environment variable.
"""

from __future__ import annotations

import json
import os
import pathlib
import unittest

from hep_agent.models import AgentProfile, ModelResponse
from hep_agent.models.semantic_process import (
    SemanticPlanningError,
    compile_semantic_process_workflow,
    plan_semantic_process,
)
from hep_agent.orchestration import (
    PreExecutionStatus,
    run_preexecution_loop,
)


def _scenarios_path() -> pathlib.Path:
    override = os.environ.get("HEP_ACCEPTANCE_SCENARIOS")
    if override:
        return pathlib.Path(override)
    return pathlib.Path(__file__).parent / "acceptance" / "scenarios.json"


SCENARIOS = json.loads(_scenarios_path().read_text())

PROFILE = AgentProfile(
    primary_model="acceptance",
    primary_timeout_seconds=180,
    max_repairs=2,
)


class ReplayClient:
    """Replays recorded raw model outputs in order."""

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.models: list[str] = []

    def chat(self, **kwargs) -> ModelResponse:
        self.models.append(kwargs["model"])
        if not self.outputs:
            raise AssertionError(
                "Scenario ran out of recorded model outputs; the pipeline "
                "asked for more model calls than were recorded."
            )
        return ModelResponse(
            model=kwargs["model"],
            content=self.outputs.pop(0),
            total_duration_ns=1_000_000_000,
        )


def _generate_line(commands) -> str | None:
    for command in commands:
        if command.startswith("generate"):
            return command
    return None


def _assert_expect(test, expect, *, workflow, generate_line) -> None:
    if "generate" in expect:
        test.assertEqual(generate_line, expect["generate"])
    if "incoming" in expect:
        test.assertEqual(
            workflow.processes[0].incoming_particles, expect["incoming"]
        )
    if "final" in expect:
        finals = [
            node.particle
            for node in workflow.processes[0].final_particles
        ]
        test.assertEqual(finals, expect["final"])
    if "pythia8" in expect:
        test.assertEqual(workflow.pipeline.pythia8, expect["pythia8"])
    if "delphes" in expect:
        test.assertEqual(workflow.pipeline.delphes, expect["delphes"])
    if "nevents" in expect:
        test.assertEqual(workflow.run.nevents, expect["nevents"])
    if "model_name" in expect:
        test.assertEqual(workflow.model.name, expect["model_name"])


def _run_full(test, scenario) -> None:
    expect = scenario.get("expect", {})
    outcome = expect.get("outcome")
    client = ReplayClient(scenario["model_outputs"])
    result = run_preexecution_loop(
        scenario["request"], client=client, profile=PROFILE
    )

    if outcome in ("ready", "repaired"):
        test.assertEqual(
            result.status,
            PreExecutionStatus.READY_FOR_APPROVAL,
            msg=f"{scenario['name']}: status={result.status}",
        )
        if outcome == "repaired":
            test.assertGreaterEqual(result.repair_attempts, 1)
        generate_line = (
            _generate_line(result.artifact.commands)
            if result.artifact is not None
            else None
        )
        _assert_expect(
            test,
            expect,
            workflow=result.workflow,
            generate_line=generate_line,
        )
    elif outcome == "blocked":
        test.assertNotEqual(
            result.status,
            PreExecutionStatus.READY_FOR_APPROVAL,
            msg=f"{scenario['name']}: expected blocked, got ready",
        )
    else:
        test.fail(f"Unknown full-route outcome: {outcome!r}")


def _run_semantic(test, scenario) -> None:
    expect = scenario.get("expect", {})
    outcome = expect.get("outcome")
    client = ReplayClient(scenario["model_outputs"])

    if outcome == "error":
        with test.assertRaises((SemanticPlanningError, ValueError)):
            planned = plan_semantic_process(
                scenario["request"], client=client, model="acceptance"
            )
            compile_semantic_process_workflow(
                scenario["request"],
                planned.process_command,
                pythia8_hint=planned.pythia8,
                delphes_hint=planned.delphes,
            )
        return

    planned = plan_semantic_process(
        scenario["request"], client=client, model="acceptance"
    )
    workflow = compile_semantic_process_workflow(
        scenario["request"],
        planned.process_command,
        pythia8_hint=planned.pythia8,
        delphes_hint=planned.delphes,
    )
    _assert_expect(
        test,
        expect,
        workflow=workflow,
        generate_line=planned.process_command,
    )


def _make_test(scenario):
    def test(self):
        if not scenario.get("model_outputs"):
            reason = scenario.get(
                "record_error", "no model_outputs recorded"
            )
            self.skipTest(f"{scenario['name']}: {reason}")
        route = scenario.get("route")
        if route == "full":
            _run_full(self, scenario)
        elif route == "semantic":
            _run_semantic(self, scenario)
        else:
            self.fail(f"Unknown route: {route!r}")

    return test


class AcceptanceTests(unittest.TestCase):
    pass


for _scenario in SCENARIOS:
    setattr(
        AcceptanceTests,
        "test_" + _scenario["name"],
        _make_test(_scenario),
    )


if __name__ == "__main__":
    unittest.main()
