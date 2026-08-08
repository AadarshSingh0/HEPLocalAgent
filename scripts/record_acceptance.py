#!/usr/bin/env python3
"""Record real local-model outputs for the acceptance scenarios.

The acceptance harness (``tests/test_acceptance.py``) replays recorded model
outputs through the real pipeline. The committed
``tests/acceptance/scenarios.json`` uses representative outputs so CI is green
without a running model. This script captures *actual* outputs from a local
Ollama model, so you can validate how a specific model handles each request.

Workflow
--------
1. Run the model on every scenario that has a ``request`` and record its raw
   output:

       python scripts/record_acceptance.py \\
           --in tests/acceptance/scenarios.template.json \\
           --out tests/acceptance/scenarios.qwen7b.json \\
           --model qwen2.5-coder:7b

   (add ``--ollama-host http://host:11434`` if Ollama is not on localhost.)

2. Point the harness at the recorded file and run it:

       HEP_ACCEPTANCE_SCENARIOS=tests/acceptance/scenarios.qwen7b.json \\
           python -m unittest tests.test_acceptance -v

Notes
-----
* Each scenario is recorded with a single planner output. Scenarios that expect
  a repair (outcome ``repaired``) need a second, corrected output appended to
  ``model_outputs`` by hand; the recorder cannot know the repair a model would
  produce without running the whole loop.
* Recording never modifies the committed scenarios file - it writes to
  ``--out``.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from hep_agent.models.ollama import OllamaClient, OllamaClientError
from hep_agent.models.planner import PlannerError, plan_workflow
from hep_agent.models.semantic_process import (
    SemanticPlanningError,
    plan_semantic_process,
)


def _record_one(scenario: dict, client: OllamaClient, model: str) -> None:
    request = scenario["request"]
    route = scenario.get("route")

    if route == "semantic":
        planned = plan_semantic_process(
            request, client=client, model=model
        )
        scenario["model_outputs"] = [planned.model_response.content]
    elif route == "full":
        planned = plan_workflow(request, client=client, model=model)
        scenario["model_outputs"] = [planned.raw_content]
    else:
        raise ValueError(f"unknown route: {route!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="inp", required=True)
    parser.add_argument("--out", dest="out", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--ollama-host", dest="host", default=None)
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Only record scenarios that have no model_outputs yet.",
    )
    args = parser.parse_args(argv)

    client = OllamaClient(host=args.host)
    scenarios = json.loads(pathlib.Path(args.inp).read_text())

    recorded = 0
    for scenario in scenarios:
        name = scenario.get("name", "<unnamed>")
        if args.only_missing and scenario.get("model_outputs"):
            continue
        try:
            _record_one(scenario, client, args.model)
            recorded += 1
            print(f"recorded: {name}")
        except (
            OllamaClientError,
            PlannerError,
            SemanticPlanningError,
            ValueError,
        ) as exc:
            scenario["record_error"] = str(exc)
            print(f"FAILED  : {name}: {exc}", file=sys.stderr)

    pathlib.Path(args.out).write_text(
        json.dumps(scenarios, indent=2) + "\n"
    )
    print(f"\nwrote {args.out} ({recorded} recorded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
