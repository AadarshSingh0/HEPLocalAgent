"""Validator-guided repair of structured collider workflows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from hep_agent.models.ollama import ModelResponse, OllamaClient
from hep_agent.models.planner import parse_planner_content
from hep_agent.schemas import WorkflowIntent
from hep_agent.validation import ValidationReport


@dataclass(frozen=True)
class RepairResult:
    """Repaired workflow and local-model metadata."""

    workflow: WorkflowIntent
    model_response: ModelResponse

    @property
    def raw_content(self) -> str:
        return self.model_response.content


def default_repair_prompt_path() -> Path:
    """Return the repository repair-prompt path."""

    project_root = Path(__file__).resolve().parents[3]
    return project_root / "prompts" / "repair_system.txt"


def load_repair_prompt(
    path: str | Path | None = None,
) -> str:
    """Load the repair system prompt."""

    prompt_path = (
        Path(path)
        if path is not None
        else default_repair_prompt_path()
    )

    return prompt_path.read_text(encoding="utf-8").strip()


def _format_validator_feedback(
    report: ValidationReport,
) -> list[dict[str, str | None]]:
    """Convert validation errors into model-readable JSON."""

    return [
        {
            "code": issue.code,
            "message": issue.message,
            "path": issue.path,
        }
        for issue in report.errors
    ]


def repair_workflow(
    *,
    user_request: str,
    invalid_workflow: WorkflowIntent,
    validation_report: ValidationReport,
    client: OllamaClient,
    model: str,
    timeout_seconds: int = 180,
    prompt_path: str | Path | None = None,
) -> RepairResult:
    """Repair one invalid structured workflow."""

    if not user_request.strip():
        raise ValueError("user_request cannot be blank.")

    if not validation_report.errors:
        raise ValueError(
            "repair_workflow requires at least one validation error."
        )

    system_prompt = load_repair_prompt(prompt_path)

    repair_payload = {
        "original_user_request": user_request,
        "invalid_workflow": invalid_workflow.model_dump(mode="json"),
        "validator_errors": _format_validator_feedback(
            validation_report
        ),
    }

    response = client.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": json.dumps(
                    repair_payload,
                    indent=2,
                ),
            },
        ],
        response_schema=WorkflowIntent.model_json_schema(),
        temperature=0.0,
        num_predict=4096,
        timeout_seconds=timeout_seconds,
    )

    workflow = parse_planner_content(response.content)

    return RepairResult(
        workflow=workflow,
        model_response=response,
    )
