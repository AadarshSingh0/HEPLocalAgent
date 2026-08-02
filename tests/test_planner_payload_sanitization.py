"""Regression tests for planner payload sanitization."""

import json
import unittest
from unittest.mock import patch

from hep_agent.models.planner import (
    parse_planner_content,
)


class PlannerPayloadSanitizationTests(
    unittest.TestCase
):
    def test_parser_normalizes_duplicate_process_ids(
        self,
    ) -> None:
        raw_response = json.dumps(
            {
                "task_type": "run_simulation",
                "processes": [
                    {
                        "process_id": "signal",
                        "incoming_particles": [
                            "p",
                            "p",
                        ],
                        "final_particles": [
                            {
                                "particle": "e+",
                                "decays": [],
                            },
                            {
                                "particle": "e-",
                                "decays": [],
                            },
                        ],
                    },
                    {
                        "process_id": "signal",
                        "incoming_particles": [
                            "q",
                            "q~",
                        ],
                        "final_particles": [
                            {
                                "particle": "e+",
                                "decays": [],
                            },
                            {
                                "particle": "e-",
                                "decays": [],
                            },
                        ],
                    },
                ],
            }
        )

        sentinel = object()

        with (
            patch(
                "hep_agent.models.planner."
                "WorkflowIntent.model_validate",
                return_value=sentinel,
            ) as model_validate,
            patch(
                "hep_agent.models.planner."
                "_complete_provenance",
                side_effect=lambda workflow: workflow,
            ),
        ):
            result = parse_planner_content(
                raw_response
            )

        self.assertIs(result, sentinel)

        submitted_payload = (
            model_validate.call_args.args[0]
        )

        self.assertEqual(
            [
                process["process_id"]
                for process
                in submitted_payload["processes"]
            ],
            [
                "signal",
                "process_002",
            ],
        )

    def test_parser_removes_exact_duplicate_processes(
        self,
    ) -> None:
        duplicate_process = {
            "process_id": "signal",
            "incoming_particles": [
                "p",
                "p",
            ],
            "final_particles": [
                {
                    "particle": "e+",
                    "decays": [],
                },
                {
                    "particle": "e-",
                    "decays": [],
                },
            ],
        }

        raw_response = json.dumps(
            {
                "task_type": "run_simulation",
                "processes": [
                    duplicate_process,
                    duplicate_process,
                ],
            }
        )

        with (
            patch(
                "hep_agent.models.planner."
                "WorkflowIntent.model_validate",
                return_value=object(),
            ) as model_validate,
            patch(
                "hep_agent.models.planner."
                "_complete_provenance",
                side_effect=lambda workflow: workflow,
            ),
        ):
            parse_planner_content(
                raw_response
            )

        submitted_payload = (
            model_validate.call_args.args[0]
        )

        self.assertEqual(
            len(
                submitted_payload[
                    "processes"
                ]
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
