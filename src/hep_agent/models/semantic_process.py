"""Thin semantic planning for collider-process requests.

The LLM performs one narrow interpretation task:

    natural language -> one MadGraph generate command
                        + parton-shower / detector-stage intent

All remaining workflow construction is deterministic. Process syntax and
execution stay under deterministic control; only the interpretation of which
stages the user asked for is model-led, with explicit deterministic anchors
taking precedence when present.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from hep_agent.models.ollama import (
    ModelResponse,
    OllamaClient,
)
from hep_agent.schemas import WorkflowIntent
from hep_agent.validation.analysis_request import (
    extract_analysis_request_facts,
)
from hep_agent.validation.grounding import (
    extract_explicit_request_facts,
)


SEMANTIC_PROCESS_PROMPT = """You translate a collider-simulation request into a MadGraph process and pipeline-stage decisions.

Return a JSON object with exactly these fields:
- "process": one command beginning with "generate", using MadGraph particle labels. Preserve explicitly requested decay chains and intermediate particles. Do not include event counts, collider energies, or coupling-order restrictions unless explicitly requested.
- "pythia8": "on" if the user wants parton showering / hadronisation / Pythia; "off" if they explicitly do not; "unspecified" if they do not mention it.
- "delphes": "on" if the user wants detector simulation / Delphes; "off" if they explicitly do not; "unspecified" if they do not mention it.

Interpret meaning, not exact words. Treat "turn on Pythia", "enable showering", "shower the events", "include parton shower", and "with Pythia8" as pythia8 = "on". Treat "parton level only", "no showering", and "do not shower" as pythia8 = "off". Treat "detector simulation", "with Delphes", and "reconstruct with Delphes" as delphes = "on"; treat "no detector simulation" and "switch Delphes off" as delphes = "off". If a stage is not mentioned, use "unspecified".

Examples:

Request: Produce an electron pair in proton-proton collisions.
JSON: {"process": "generate p p > e+ e-", "pythia8": "unspecified", "delphes": "unspecified"}

Request: Produce a Z boson and decay it to an electron and a positron, and turn on Pythia.
JSON: {"process": "generate p p > z, z > e+ e-", "pythia8": "on", "delphes": "unspecified"}

Request: Top pair production, parton level only, no detector simulation.
JSON: {"process": "generate p p > t t~", "pythia8": "off", "delphes": "off"}
"""


# JSON schema constraining the semantic planner's structured output. Stage
# fields use an explicit three-value enum so "unspecified" is distinguishable
# from "off": the model must not silently default a stage the user did not
# mention.
SEMANTIC_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "process": {"type": "string"},
        "pythia8": {
            "type": "string",
            "enum": ["on", "off", "unspecified"],
        },
        "delphes": {
            "type": "string",
            "enum": ["on", "off", "unspecified"],
        },
    },
    "required": ["process", "pythia8", "delphes"],
}


class SemanticPlanningError(ValueError):
    """A safe semantic-planning or compilation failure."""

    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ParsedSemanticProcess:
    """Deterministic representation of one generate command."""

    incoming_particles: tuple[str, ...]
    final_particles: tuple[str, ...]
    required_intermediates: tuple[str, ...]
    decays: tuple[
        tuple[str, tuple[str, ...]],
        ...,
    ]


@dataclass(frozen=True)
class SemanticProcessResult:
    """Semantic command, model-interpreted stage intent, and metadata.

    ``pythia8`` and ``delphes`` are the model's interpretation of whether the
    user asked for those stages: ``True`` (on), ``False`` (off), or ``None``
    (the user did not mention the stage). Explicit deterministic anchors, when
    present, still take precedence over these during compilation.
    """

    process_command: str
    model_response: ModelResponse
    pythia8: bool | None = None
    delphes: bool | None = None

    @property
    def raw_content(self) -> str:
        return self.model_response.content


def _normalise(text: str) -> str:
    return " ".join(text.split())


def _requires_channel_clarification(
    user_request: str,
) -> bool:
    """Detect ambiguous natural-language channel restrictions."""

    text = " ".join(
        user_request.lower().split()
    )

    return bool(
        re.search(
            (
                r"\b(?:through|via)\b"
                r"[^.!?;]{0,80}"
                r"\b(?:only|channel|intermediate)\b"
            ),
            text,
        )
    )


def ensure_semantic_request_supported(
    user_request: str,
) -> None:
    """Block requests whose channel semantics need clarification."""

    if _requires_channel_clarification(
        user_request
    ):
        raise SemanticPlanningError(
            "ambiguous_channel_request",
            (
                "The request constrains a channel using "
                "natural-language wording that can map to "
                "different MadGraph constructions. Ask whether "
                "the user wants resonant production with decay "
                "or exclusion of non-mediator diagrams."
            ),
        )


def extract_generate_command(
    content: str,
) -> str:
    """Extract exactly one generate command from model output."""

    cleaned = (
        content
        .replace("```madgraph", "")
        .replace("```text", "")
        .replace("```", "")
        .strip()
    )

    commands = [
        _normalise(line.strip())
        for line in cleaned.splitlines()
        if line.strip().lower().startswith(
            "generate "
        )
    ]

    if len(commands) != 1:
        raise SemanticPlanningError(
            "invalid_semantic_output",
            (
                "The semantic planner must return exactly "
                "one MadGraph generate command."
            ),
        )

    return commands[0]


def _stage_to_optional_bool(value: object) -> bool | None:
    """Map an "on"/"off"/"unspecified" stage token to True/False/None."""

    if value == "on":
        return True
    if value == "off":
        return False
    return None


def parse_semantic_planner_output(
    content: str,
) -> tuple[str, bool | None, bool | None]:
    """Parse the semantic planner's output into command and stage intent.

    Accepts the structured JSON object, and falls back to a bare ``generate``
    line for backward compatibility. Returned stage values are True (on),
    False (off), or None (unspecified).
    """

    cleaned = (
        content
        .replace("```json", "")
        .replace("```", "")
        .strip()
    )

    data: object = None
    try:
        data = json.loads(cleaned)
    except (ValueError, TypeError):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
            except (ValueError, TypeError):
                data = None

    if isinstance(data, dict) and isinstance(
        data.get("process"), str
    ):
        command = extract_generate_command(
            data["process"]
        )
        return (
            command,
            _stage_to_optional_bool(data.get("pythia8")),
            _stage_to_optional_bool(data.get("delphes")),
        )

    # Fallback: a bare generate line carrying no stage information.
    return extract_generate_command(content), None, None


def plan_semantic_process(
    user_request: str,
    *,
    client: OllamaClient,
    model: str,
    timeout_seconds: int = 300,
) -> SemanticProcessResult:
    """Translate one natural-language request to a process command.

    The model additionally interprets whether the user asked for the Pythia8
    and Delphes stages. The process syntax remains deterministically parsed and
    validated downstream.
    """

    if not user_request.strip():
        raise ValueError(
            "user_request cannot be blank."
        )

    ensure_semantic_request_supported(
        user_request
    )

    response = client.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    SEMANTIC_PROCESS_PROMPT
                ),
            },
            {
                "role": "user",
                "content": user_request,
            },
        ],
        response_schema=SEMANTIC_OUTPUT_SCHEMA,
        temperature=0.0,
        num_predict=300,
        timeout_seconds=timeout_seconds,
    )

    command, pythia8, delphes = (
        parse_semantic_planner_output(
            response.content
        )
    )

    return SemanticProcessResult(
        process_command=command,
        model_response=response,
        pythia8=pythia8,
        delphes=delphes,
    )


def _tokens(
    expression: str,
    *,
    label: str,
) -> tuple[str, ...]:
    tokens = tuple(
        token
        for token in expression.split()
        if token
    )

    if not tokens:
        raise SemanticPlanningError(
            "invalid_process_expression",
            f"{label} cannot be empty.",
        )

    return tokens


def _arrow_parts(
    expression: str,
) -> tuple[str, ...]:
    normalised = expression.replace(
        "->",
        ">",
    )

    parts = tuple(
        _normalise(part)
        for part in normalised.split(">")
    )

    if (
        len(parts) < 2
        or any(not part for part in parts)
    ):
        raise SemanticPlanningError(
            "invalid_process_expression",
            (
                "Every process clause must contain "
                "valid MadGraph arrow syntax."
            ),
        )

    return parts


def parse_semantic_process_command(
    process_command: str,
) -> ParsedSemanticProcess:
    """Parse restricted generic MadGraph process syntax."""

    command = _normalise(
        process_command
    )

    if not command.lower().startswith(
        "generate "
    ):
        raise SemanticPlanningError(
            "missing_generate_command",
            (
                "The semantic command must begin "
                "with 'generate'."
            ),
        )

    expression = command[
        len("generate "):
    ].strip()

    if any(
        character in expression
        for character in (
            "\n",
            "\r",
            ";",
            "`",
            "@",
            "=",
        )
    ):
        raise SemanticPlanningError(
            "unsafe_process_expression",
            (
                "The semantic command contains an "
                "unsupported restriction or character."
            ),
        )

    if re.search(
        (
            r"\b(?:tev|gev|events?|nevents|"
            r"beamm|ebeam1|ebeam2)\b"
        ),
        expression,
        re.IGNORECASE,
    ):
        raise SemanticPlanningError(
            "process_contains_run_settings",
            (
                "Energy and event settings must not "
                "appear in the process expression."
            ),
        )

    clauses = [
        clause.strip()
        for clause in expression.split(",")
        if clause.strip()
    ]

    if not clauses:
        raise SemanticPlanningError(
            "empty_process_expression",
            "The process expression is empty.",
        )

    main_parts = _arrow_parts(
        clauses[0]
    )

    incoming = _tokens(
        main_parts[0],
        label="Incoming state",
    )

    if len(main_parts) == 2:
        intermediates: tuple[str, ...] = ()
        final = _tokens(
            main_parts[1],
            label="Final state",
        )

    elif len(main_parts) == 3:
        intermediates = _tokens(
            main_parts[1],
            label="Intermediate state",
        )

        if len(intermediates) != 1:
            raise SemanticPlanningError(
                "multiple_required_intermediates",
                (
                    "Version 1 supports one explicit "
                    "required intermediate."
                ),
            )

        final = _tokens(
            main_parts[2],
            label="Final state",
        )

    else:
        raise SemanticPlanningError(
            "unsupported_arrow_depth",
            (
                "Version 1 supports an inclusive "
                "process or one explicit intermediate."
            ),
        )

    decays: list[
        tuple[str, tuple[str, ...]]
    ] = []

    seen_parents: set[str] = set()

    for clause in clauses[1:]:
        decay_parts = _arrow_parts(
            clause.strip("() ")
        )

        if len(decay_parts) != 2:
            raise SemanticPlanningError(
                "unsupported_decay_clause",
                (
                    "Each decay clause must have the "
                    "form 'parent > daughters'."
                ),
            )

        parent_tokens = _tokens(
            decay_parts[0],
            label="Decay parent",
        )

        if len(parent_tokens) != 1:
            raise SemanticPlanningError(
                "invalid_decay_parent",
                (
                    "Each decay clause must contain "
                    "one parent particle."
                ),
            )

        parent = parent_tokens[0]
        daughters = _tokens(
            decay_parts[1],
            label="Decay products",
        )

        if parent not in final:
            raise SemanticPlanningError(
                "decay_parent_not_produced",
                (
                    f"Decay parent {parent!r} is not "
                    "a top-level produced particle."
                ),
            )

        if parent in seen_parents:
            raise SemanticPlanningError(
                "duplicate_decay_parent",
                (
                    f"More than one decay clause was "
                    f"provided for {parent!r}."
                ),
            )

        seen_parents.add(parent)

        decays.append(
            (
                parent,
                daughters,
            )
        )

    return ParsedSemanticProcess(
        incoming_particles=incoming,
        final_particles=final,
        required_intermediates=(
            intermediates
        ),
        decays=tuple(decays),
    )


def _infer_collider_type(
    beams: tuple[str, ...],
) -> str:
    if beams == ("p", "p"):
        return "hadron"

    leptons = {
        "e+",
        "e-",
        "mu+",
        "mu-",
    }

    if (
        len(beams) == 2
        and set(beams).issubset(leptons)
    ):
        return "lepton"

    return "partonic"


def _resolve_stage(
    explicit: bool | None,
    model_hint: bool | None,
) -> tuple[bool, str]:
    """Resolve a pipeline stage from a deterministic anchor and model intent.

    Precedence: an explicit deterministic anchor (a phrase the grounding
    extractor recognised) wins; otherwise the model's interpretation stands;
    otherwise the stage defaults to off. The second element records provenance
    for the workflow's field_sources.
    """

    if explicit is not None:
        return explicit, "user"
    if model_hint is not None:
        return model_hint, "model_inference"
    return False, "validated_default"


def compile_semantic_process_workflow(
    user_request: str,
    process_command: str,
    *,
    pythia8_hint: bool | None = None,
    delphes_hint: bool | None = None,
) -> WorkflowIntent:
    """Compile a semantic command into the full internal workflow.

    ``pythia8_hint`` and ``delphes_hint`` are the model's interpretation of the
    requested stages; explicit deterministic anchors take precedence over them.
    """

    ensure_semantic_request_supported(
        user_request
    )

    parsed = (
        parse_semantic_process_command(
            process_command
        )
    )

    facts = extract_explicit_request_facts(
        user_request
    )

    analysis_facts = (
        extract_analysis_request_facts(
            user_request
        )
    )

    if facts.energy_gev is None:
        raise SemanticPlanningError(
            "missing_energy",
            (
                "A collider energy is required "
                "before workflow construction."
            ),
        )

    if facts.nevents is None:
        raise SemanticPlanningError(
            "missing_event_count",
            (
                "An event count is required "
                "before workflow construction."
            ),
        )

    collider_beams = (
        facts.collider_beams
        or tuple(
            parsed.incoming_particles[:2]
        )
    )

    if len(collider_beams) != 2:
        raise SemanticPlanningError(
            "invalid_collider_beams",
            (
                "Exactly two collider beams "
                "are required."
            ),
        )

    decay_map = {
        parent: daughters
        for parent, daughters
        in parsed.decays
    }

    final_nodes = []

    for particle in (
        parsed.final_particles
    ):
        daughters = decay_map.get(
            particle,
            (),
        )

        final_nodes.append(
            {
                "particle": particle,
                "decay_products": [
                    {
                        "particle": daughter,
                    }
                    for daughter
                    in daughters
                ],
            }
        )

    pythia8_value, pythia8_source = _resolve_stage(
        facts.pythia8, pythia8_hint
    )
    delphes_value, delphes_source = _resolve_stage(
        facts.delphes, delphes_hint
    )

    workflow_payload = {
        "schema_version": "1.0",
        "task_type": "run_simulation",
        "model": {
            "name": (
                facts.model_name
                or "sm"
            ),
            "source": "builtin",
            "model_path": None,
        },
        "collider": {
            "collider_type": (
                _infer_collider_type(
                    collider_beams
                )
            ),
            "beams": [
                {
                    "particle": particle,
                }
                for particle
                in collider_beams
            ],
            "energy": {
                "value_gev": (
                    facts.energy_gev
                ),
                "meaning": (
                    facts.energy_meaning.value
                    if facts.energy_meaning
                    is not None
                    else (
                        "total_center_of_mass"
                    )
                ),
            },
        },
        "processes": [
            {
                "process_id": (
                    "semantic_process_001"
                ),
                "incoming_particles": list(
                    parsed.incoming_particles
                ),
                "final_particles": (
                    final_nodes
                ),
                "required_intermediates": list(
                    parsed
                    .required_intermediates
                ),
                "excluded_particles": [],
                "coupling_orders": {},
            }
        ],
        "run": {
            "nevents": facts.nevents,
            "random_seed": None,
            "timeout_seconds": 1800,
            "output_name": None,
        },
        "pipeline": {
            "madgraph": True,
            "pythia8": pythia8_value,
            "delphes": delphes_value,
            "madanalysis": (
                analysis_facts
                .madanalysis_choice
                is True
            ),
        },
        "analysis": None,
        "field_sources": {
            "model.name": (
                "validated_default"
            ),
            "collider.beams": "user",
            (
                "collider.energy."
                "value_gev"
            ): "user",
            "processes": (
                "model_inference"
            ),
            "run.nevents": "user",
            "pipeline.pythia8": pythia8_source,
            "pipeline.delphes": delphes_source,
            "pipeline.madanalysis": (
                "user"
                if analysis_facts
                .madanalysis_choice
                is not None
                else "validated_default"
            ),
        },
        "notes": [
            (
                "Process semantics were translated "
                "by the thin semantic planner and "
                "compiled deterministically."
            )
        ],
    }

    return WorkflowIntent.model_validate(
        workflow_payload
    )
