"""Structured local-LLM planner for collider workflows."""

from __future__ import annotations

from hep_agent.models.workflow_payload import (
    sanitize_workflow_payload,
)

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pydantic import ValidationError

from hep_agent.models.ollama import (
    ModelResponse,
    OllamaClient,
)
from hep_agent.schemas import (
    FieldSource,
    WorkflowIntent,
)


# Built-in model spellings we recognise. Keys have case, spaces, underscores,
# and hyphens removed, so "sm", "SM", "Standard Model", "Standard_Model", and
# "StandardModel" all resolve to the same canonical name. loop_sm shares the
# Standard Model particle content. A genuine UFO name we do not recognise is
# left untouched.
_BUILTIN_MODEL_CANONICAL = {
    "sm": "sm",
    "standardmodel": "sm",
    "loopsm": "loop_sm",
}


def _canonical_builtin_model_name(name: object) -> str | None:
    """Return the canonical built-in model name for a spelling, or None."""

    if not isinstance(name, str):
        return None

    key = re.sub(r"[\s_\-]+", "", name.strip().lower())
    return _BUILTIN_MODEL_CANONICAL.get(key)


class PlannerFailureType(str, Enum):
    INVALID_JSON = "invalid_json"
    SCHEMA_VALIDATION = "schema_validation_failure"


class PlannerError(ValueError):
    """Semantic failure while interpreting planner output."""

    def __init__(
        self,
        message: str,
        *,
        failure_type: PlannerFailureType,
        raw_content: str,
    ) -> None:
        super().__init__(message)
        self.failure_type = failure_type
        self.raw_content = raw_content


@dataclass(frozen=True)
class PlannerResult:
    """Structured workflow and model metadata."""

    workflow: WorkflowIntent
    model_response: ModelResponse

    @property
    def raw_content(self) -> str:
        return self.model_response.content


def default_prompt_path() -> Path:
    """Return the repository planner-prompt path."""

    project_root = Path(__file__).resolve().parents[3]
    return project_root / "prompts" / "planner_system.txt"


def load_planner_prompt(
    path: str | Path | None = None,
) -> str:
    """Load the planner system prompt."""

    prompt_path = (
        Path(path)
        if path is not None
        else default_prompt_path()
    )

    return prompt_path.read_text(encoding="utf-8").strip()


def _complete_provenance(
    workflow: WorkflowIntent,
) -> WorkflowIntent:
    """Conservatively fill missing provenance information.

    Missing physics-critical provenance is treated as model inference.
    Missing ordinary run and pipeline provenance is treated as a
    validated default.
    """

    sources = dict(workflow.field_sources)

    physics_critical_defaults = {
        "model.name": FieldSource.MODEL_INFERENCE,
        "collider.beams": FieldSource.MODEL_INFERENCE,
        "collider.energy.value_gev": FieldSource.MODEL_INFERENCE,
        "processes": FieldSource.MODEL_INFERENCE,
    }

    ordinary_defaults = {
        "run.nevents": FieldSource.VALIDATED_DEFAULT,
        "pipeline.pythia8": FieldSource.VALIDATED_DEFAULT,
        "pipeline.delphes": FieldSource.VALIDATED_DEFAULT,
        "pipeline.madanalysis": FieldSource.VALIDATED_DEFAULT,
    }

    if workflow.analysis is not None:
        sources.setdefault(
            "analysis",
            FieldSource.MODEL_INFERENCE,
        )

    for path, source in physics_critical_defaults.items():
        sources.setdefault(path, source)

    for path, source in ordinary_defaults.items():
        sources.setdefault(path, source)

    workflow.field_sources = sources
    return workflow



def _normalize_known_builtin_model_payload(
    payload: object,
) -> object:
    """Correct safe, recognised built-in model classifications.

    Local models sometimes correctly identify a built-in model (the Standard
    Model or loop_sm) but mislabel it as a user UFO, or spell its name in a
    way the schema does not expect ("StandardModel"). We normalise any
    recognised built-in spelling to its canonical name, and additionally
    repair a built-in mislabelled as a user UFO when no model path is given.
    Genuine, unrecognised UFO names are left untouched.
    """

    if not isinstance(payload, dict):
        return payload

    model = payload.get("model")

    if not isinstance(model, dict):
        return payload

    name = model.get("name")
    source = model.get("source")
    model_path = model.get("model_path")

    if not isinstance(name, str):
        return payload

    canonical_name = _canonical_builtin_model_name(name)

    if canonical_name is not None:
        # Normalise the spelling so the compiler emits the correct built-in
        # model name and downstream domain validation is authoritative.
        model["name"] = canonical_name

        # A recognised built-in model mislabelled as a user UFO (with no
        # path) is corrected back to a built-in source.
        if source == "user_ufo" and not model_path:
            model["source"] = "builtin"
            model["model_path"] = None

    return payload

def parse_planner_content(content: str) -> WorkflowIntent:
    """Parse strict JSON planner output into WorkflowIntent."""

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise PlannerError(
            "The planner did not return valid JSON.",
            failure_type=PlannerFailureType.INVALID_JSON,
            raw_content=content,
        ) from exc

    payload = _normalize_known_builtin_model_payload(payload)

    try:
        sanitized_payload = sanitize_workflow_payload(
            payload
        )
        workflow = WorkflowIntent.model_validate(
            sanitized_payload
        )
    except ValidationError as exc:
        raise PlannerError(
            f"The planner JSON failed schema validation: {exc}",
            failure_type=PlannerFailureType.SCHEMA_VALIDATION,
            raw_content=content,
        ) from exc

    return _complete_provenance(workflow)


def plan_workflow(
    user_request: str,
    *,
    client: OllamaClient,
    model: str,
    timeout_seconds: int = 180,
    prompt_path: str | Path | None = None,
) -> PlannerResult:
    """Convert one user request into a structured workflow."""

    if not user_request.strip():
        raise ValueError("user_request cannot be blank.")

    system_prompt = load_planner_prompt(prompt_path)

    response = client.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_request,
            },
        ],
        response_schema=WorkflowIntent.model_json_schema(),
        temperature=0.0,
        num_predict=4096,
        timeout_seconds=timeout_seconds,
    )

    workflow = parse_planner_content(response.content)

    return PlannerResult(
        workflow=workflow,
        model_response=response,
    )
