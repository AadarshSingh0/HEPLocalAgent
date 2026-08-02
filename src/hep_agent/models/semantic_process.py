"""Thin semantic planning for collider-process requests.

The LLM performs one narrow task:

    natural language -> one MadGraph generate command

All remaining workflow construction is deterministic.
"""

from __future__ import annotations

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


SEMANTIC_PROCESS_PROMPT = """You translate collider-simulation requests into MadGraph process syntax.

Return exactly one line beginning with:

generate

Do not return JSON.
Do not explain.
Do not include event counts or collider energies.
Do not add coupling-order restrictions unless explicitly requested.
Use MadGraph particle labels.
Preserve explicitly requested decay chains and intermediate particles.

Examples:

Request:
Produce an electron pair in proton-proton collisions.

Answer:
generate p p > e+ e-

Request:
Produce a Z boson and decay it to an electron and a positron.

Answer:
generate p p > z, z > e+ e-

Request:
Produce a W+ boson and decay it to a positron and electron neutrino.

Answer:
generate p p > w+, w+ > e+ ve

Request:
Use an explicit Z intermediate for electron-neutrino pair production.

Answer:
generate p p > z > ve ve~
"""


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
    """Semantic command plus model metadata."""

    process_command: str
    model_response: ModelResponse

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


def plan_semantic_process(
    user_request: str,
    *,
    client: OllamaClient,
    model: str,
    timeout_seconds: int = 300,
) -> SemanticProcessResult:
    """Translate one natural-language request to a process command."""

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
        response_schema=None,
        temperature=0.0,
        num_predict=300,
        timeout_seconds=timeout_seconds,
    )

    command = extract_generate_command(
        response.content
    )

    return SemanticProcessResult(
        process_command=command,
        model_response=response,
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


def compile_semantic_process_workflow(
    user_request: str,
    process_command: str,
) -> WorkflowIntent:
    """Compile a semantic command into the full internal workflow."""

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
            "pythia8": bool(
                facts.pythia8
            ),
            "delphes": bool(
                facts.delphes
            ),
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
            "pipeline.pythia8": (
                "user"
                if facts.pythia8
                is not None
                else "validated_default"
            ),
            "pipeline.delphes": (
                "user"
                if facts.delphes
                is not None
                else "validated_default"
            ),
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
