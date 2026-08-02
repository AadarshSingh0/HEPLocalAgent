"""Tests for safe pre-validation workflow JSON normalization."""

import json
import unittest

from hep_agent.models.workflow_payload import (
    sanitize_workflow_json,
    sanitize_workflow_payload,
)


def process(
    process_id: str,
    final_particle: str,
) -> dict:
    return {
        "process_id": process_id,
        "incoming_particles": [
            "p",
            "p",
        ],
        "final_particles": [
            {
                "particle": final_particle,
                "decays": [],
            }
        ],
    }


class WorkflowPayloadNormalizationTests(
    unittest.TestCase
):
    def test_duplicate_ids_are_renamed(
        self,
    ) -> None:
        payload = {
            "processes": [
                process("signal", "e+"),
                process("signal", "mu+"),
            ]
        }

        result = sanitize_workflow_payload(
            payload
        )

        ids = [
            item["process_id"]
            for item in result["processes"]
        ]

        self.assertEqual(
            ids,
            [
                "signal",
                "process_002",
            ],
        )

    def test_exact_duplicate_process_is_removed(
        self,
    ) -> None:
        payload = {
            "processes": [
                process("signal", "e+"),
                process("signal", "e+"),
            ]
        }

        result = sanitize_workflow_payload(
            payload
        )

        self.assertEqual(
            len(result["processes"]),
            1,
        )
        self.assertEqual(
            result["processes"][0][
                "process_id"
            ],
            "signal",
        )

    def test_missing_ids_are_created(
        self,
    ) -> None:
        first = process("", "e+")
        second = process("", "mu+")

        first.pop("process_id")
        second.pop("process_id")

        result = sanitize_workflow_payload(
            {
                "processes": [
                    first,
                    second,
                ]
            }
        )

        self.assertEqual(
            [
                item["process_id"]
                for item in result["processes"]
            ],
            [
                "process_001",
                "process_002",
            ],
        )

    def test_valid_payload_is_unchanged(
        self,
    ) -> None:
        payload = {
            "processes": [
                process("electron", "e+"),
                process("muon", "mu+"),
            ]
        }

        self.assertEqual(
            sanitize_workflow_payload(
                payload
            ),
            payload,
        )

    def test_malformed_json_is_preserved(
        self,
    ) -> None:
        malformed = '{"processes": ['

        self.assertEqual(
            sanitize_workflow_json(
                malformed
            ),
            malformed,
        )

    def test_json_normalization_produces_unique_ids(
        self,
    ) -> None:
        raw = json.dumps(
            {
                "processes": [
                    process("same", "e+"),
                    process("same", "mu+"),
                ]
            }
        )

        result = json.loads(
            sanitize_workflow_json(raw)
        )

        self.assertEqual(
            [
                item["process_id"]
                for item in result["processes"]
            ],
            [
                "same",
                "process_002",
            ],
        )


if __name__ == "__main__":
    unittest.main()
