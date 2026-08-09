"""Small Ollama client used by the local HEP agent."""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ModelFailureType(str, Enum):
    CONNECTION = "connection_failure"
    TIMEOUT = "timeout"
    HTTP = "http_failure"
    INVALID_RESPONSE = "invalid_response"


class OllamaClientError(RuntimeError):
    """Infrastructure error raised while communicating with Ollama."""

    def __init__(
        self,
        message: str,
        *,
        failure_type: ModelFailureType,
    ) -> None:
        super().__init__(message)
        self.failure_type = failure_type


@dataclass(frozen=True)
class ModelResponse:
    """Parsed response and timing metadata returned by Ollama."""

    model: str
    content: str
    total_duration_ns: int | None = None
    load_duration_ns: int | None = None
    prompt_eval_count: int | None = None
    eval_count: int | None = None

    @property
    def total_duration_seconds(self) -> float | None:
        if self.total_duration_ns is None:
            return None
        return self.total_duration_ns / 1_000_000_000


class OllamaClient:
    """Client for Ollama's native chat endpoint."""

    def __init__(self, host: str | None = None) -> None:
        resolved_host = (
            host
            or os.environ.get("OLLAMA_HOST")
            or "http://localhost:11434"
        )

        resolved_host = resolved_host.rstrip("/")

        if resolved_host.endswith("/v1"):
            resolved_host = resolved_host[:-3]

        self.host = resolved_host

    @property
    def chat_url(self) -> str:
        return f"{self.host}/api/chat"

    @property
    def tags_url(self) -> str:
        return f"{self.host}/api/tags"

    def list_models(
        self,
        *,
        timeout_seconds: int = 5,
    ) -> list[str]:
        """Return every model name reported by the Ollama host."""

        request = urllib.request.Request(
            self.tags_url,
            headers={"Accept": "application/json"},
            method="GET",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                raw_body = response.read().decode("utf-8")

        except urllib.error.HTTPError as exc:
            raise OllamaClientError(
                f"Ollama returned HTTP status {exc.code}.",
                failure_type=ModelFailureType.HTTP,
            ) from exc

        except (TimeoutError, socket.timeout) as exc:
            raise OllamaClientError(
                "The Ollama model list request timed out.",
                failure_type=ModelFailureType.TIMEOUT,
            ) from exc

        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise OllamaClientError(
                f"Could not connect to Ollama: {reason}",
                failure_type=ModelFailureType.CONNECTION,
            ) from exc

        except UnicodeDecodeError as exc:
            raise OllamaClientError(
                "Ollama returned an invalid model-list response.",
                failure_type=ModelFailureType.INVALID_RESPONSE,
            ) from exc

        try:
            parsed = json.loads(raw_body)
            models = parsed["models"]
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
        ) as exc:
            raise OllamaClientError(
                "Ollama returned an invalid model-list response.",
                failure_type=ModelFailureType.INVALID_RESPONSE,
            ) from exc

        if not isinstance(models, list):
            raise OllamaClientError(
                "Ollama returned an invalid model-list response.",
                failure_type=ModelFailureType.INVALID_RESPONSE,
            )

        names: set[str] = set()

        for item in models:
            if not isinstance(item, dict):
                continue

            name = item.get("name")

            if not isinstance(name, str):
                name = item.get("model")

            if isinstance(name, str) and name.strip():
                names.add(name.strip())

        return sorted(names, key=str.casefold)

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        num_predict: int = 2048,
        timeout_seconds: int = 180,
    ) -> ModelResponse:
        """Send one non-streaming structured chat request."""

        if not model.strip():
            raise ValueError("model cannot be blank.")

        if not messages:
            raise ValueError("messages cannot be empty.")

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
            },
        }

        if response_schema is not None:
            payload["format"] = response_schema

        request = urllib.request.Request(
            self.chat_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                raw_body = response.read().decode("utf-8")

        except urllib.error.HTTPError as exc:
            raise OllamaClientError(
                f"Ollama returned HTTP status {exc.code}.",
                failure_type=ModelFailureType.HTTP,
            ) from exc

        except (TimeoutError, socket.timeout) as exc:
            raise OllamaClientError(
                "The Ollama request timed out.",
                failure_type=ModelFailureType.TIMEOUT,
            ) from exc

        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise OllamaClientError(
                f"Could not connect to Ollama: {reason}",
                failure_type=ModelFailureType.CONNECTION,
            ) from exc

        try:
            parsed = json.loads(raw_body)
            content = parsed["message"]["content"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise OllamaClientError(
                "Ollama returned an invalid response.",
                failure_type=ModelFailureType.INVALID_RESPONSE,
            ) from exc

        if not isinstance(content, str):
            raise OllamaClientError(
                "Ollama returned non-text message content.",
                failure_type=ModelFailureType.INVALID_RESPONSE,
            )

        return ModelResponse(
            model=str(parsed.get("model", model)),
            content=content,
            total_duration_ns=parsed.get("total_duration"),
            load_duration_ns=parsed.get("load_duration"),
            prompt_eval_count=parsed.get("prompt_eval_count"),
            eval_count=parsed.get("eval_count"),
        )
