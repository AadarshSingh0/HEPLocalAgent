"""Tests for Ollama communication and model profiles."""

import json
import unittest
import urllib.error
from unittest.mock import patch

from hep_agent.models import (
    ModelFailureType,
    OllamaClient,
    OllamaClientError,
    load_agent_profiles,
)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class ModelLayerTests(unittest.TestCase):
    def test_native_chat_endpoint_is_used(self) -> None:
        client = OllamaClient(
            "http://10.42.106.85:11434/v1"
        )

        self.assertEqual(
            client.chat_url,
            "http://10.42.106.85:11434/api/chat",
        )

    @patch("hep_agent.models.ollama.urllib.request.urlopen")
    def test_structured_chat_response(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeResponse(
            {
                "model": "test-model",
                "message": {
                    "role": "assistant",
                    "content": '{"answer": "ok"}',
                },
                "total_duration": 2_000_000_000,
                "eval_count": 12,
            }
        )

        client = OllamaClient("http://localhost:11434")

        response = client.chat(
            model="test-model",
            messages=[
                {
                    "role": "user",
                    "content": "Return JSON.",
                }
            ],
            response_schema={
                "type": "object",
                "properties": {
                    "answer": {"type": "string"}
                },
                "required": ["answer"],
            },
        )

        self.assertEqual(response.content, '{"answer": "ok"}')
        self.assertEqual(response.total_duration_seconds, 2.0)
        self.assertEqual(response.eval_count, 12)

        request = mock_urlopen.call_args.args[0]
        sent_payload = json.loads(
            request.data.decode("utf-8")
        )

        self.assertFalse(sent_payload["stream"])
        self.assertIn("format", sent_payload)

    @patch("hep_agent.models.ollama.urllib.request.urlopen")
    def test_connection_failure_is_classified(
        self,
        mock_urlopen,
    ) -> None:
        mock_urlopen.side_effect = urllib.error.URLError(
            "connection refused"
        )

        client = OllamaClient("http://localhost:11434")

        with self.assertRaises(OllamaClientError) as context:
            client.chat(
                model="test-model",
                messages=[
                    {
                        "role": "user",
                        "content": "Hello",
                    }
                ],
            )

        self.assertEqual(
            context.exception.failure_type,
            ModelFailureType.CONNECTION,
        )

    def test_agent_profiles_load(self) -> None:
        profiles = load_agent_profiles(
            "configs/agent_profiles.json"
        )

        self.assertEqual(
            profiles["legacy_llama3"].primary_model,
            "llama3:8b",
        )
        self.assertEqual(
            profiles["qwen_primary"].primary_model,
            "qwen3-coder-next:Q4_K_M",
        )
        self.assertEqual(
            profiles["qwen_cascade"].fallback_model,
            "llama3.3:70b",
        )
        self.assertTrue(
            profiles["qwen_cascade"].has_fallback
        )


if __name__ == "__main__":
    unittest.main()
