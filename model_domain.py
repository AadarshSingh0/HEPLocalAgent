"""Model-relative domain validation for collider workflows.

This is a *containment* layer, distinct from *interpretation*. Interpretation
asks "what did the user mean?" and should become more permissive as the local
model grows more capable. Containment asks "is every proposed value a real,
executable thing?" and must hold regardless of model capability, because the
failure mode of every model - small or large - is being confident and wrong.

Concretely, this module checks that every particle and multiparticle token in a
``WorkflowIntent`` actually exists in the namespace of the *selected physics
model*, before any MadGraph artifact is built or executed. A token such as
``tt~`` (two glued particles) is syntactically safe but is not a real label in
the Standard Model, so today it reaches MadGraph and fails there; this validator
stops it inside the agent instead.

The check is deliberately **model-relative**. The authority is whatever model is
loaded, not a hard-coded Standard Model list. A user who loads a richer model is
therefore not constrained to Standard Model particles: the namespace expands to
exactly what that model defines. When the namespace cannot be determined - for
example an installed or user UFO model we have not parsed yet - validation is
**permissive**: it returns no issues rather than inventing a rejection it cannot
justify. Containment must never manufacture a false block.

Suggestions are attached to every rejection so a later repair stage can correct
one field without regenerating the whole workflow. For a glued token like
``tt~`` the suggestion is the split ``["t", "t~"]``.
"""

from __future__ import annotations

from dataclasses import dataclass

from hep_agent.schemas import ModelSource, WorkflowIntent
from hep_agent.validation.core import (
    ValidationIssue,
    ValidationLevel,
    ValidationReport,
)


# ---------------------------------------------------------------------------
# Standard Model namespace
# ---------------------------------------------------------------------------
#
# These are the particle and antiparticle labels the default MadGraph ``sm``
# model exposes, plus MadGraph's default multiparticle labels. ``loop_sm``
# shares the same particle content. The generic parton labels ``q`` and ``q~``
# are included because the rest of this codebase already treats them as
# first-class partonic initial states (see ``SUPPORTED_TOTAL_COM_PAIRS`` in the
# workflow builder). A later MadGraph-preflight layer can tighten ``q``/``j``/
# ``p`` distinctions against the live model; this static layer intentionally
# errs toward accepting anything the existing pipeline already accepts.

_SM_QUARKS = {"u", "c", "d", "s", "b", "t", "q"}
_SM_QUARKS_BAR = {f"{name}~" for name in _SM_QUARKS}

_SM_CHARGED_LEPTONS = {"e-", "mu-", "ta-"}
_SM_ANTI_CHARGED_LEPTONS = {"e+", "mu+", "ta+"}

_SM_NEUTRINOS = {"ve", "vm", "vt"}
_SM_ANTI_NEUTRINOS = {f"{name}~" for name in _SM_NEUTRINOS}

# Self-conjugate bosons plus the charged-W conjugate pair.
_SM_BOSONS = {"g", "a", "z", "h", "w+", "w-"}

# MadGraph default multiparticle labels.
_SM_MULTIPARTICLES = {"p", "j", "l+", "l-", "vl", "vl~", "all"}

_SM_LABELS: frozenset[str] = frozenset(
    _SM_QUARKS
    | _SM_QUARKS_BAR
    | _SM_CHARGED_LEPTONS
    | _SM_ANTI_CHARGED_LEPTONS
    | _SM_NEUTRINOS
    | _SM_ANTI_NEUTRINOS
    | _SM_BOSONS
    | _SM_MULTIPARTICLES
)

# Built-in model names (lower-cased) whose namespace we know statically.
_KNOWN_BUILTIN_SM_NAMES = {"sm", "standard model", "standard_model", "loop_sm"}


@dataclass(frozen=True)
class ModelNamespace:
    """The set of valid particle/multiparticle labels for one model.

    ``authoritative`` is ``True`` only when we are confident the label set is
    complete for the selected model. When it is ``False`` no membership
    conclusions may be drawn, and the domain validator stays silent.
    """

    model_name: str
    labels: frozenset[str]
    authoritative: bool

    def contains(self, token: str) -> bool:
        return token.strip().lower() in self.labels


def namespace_for_model(
    workflow: WorkflowIntent,
) -> ModelNamespace:
    """Resolve the particle namespace for a workflow's selected model.

    Only built-in Standard Model variants are resolved statically today. For
    installed or user UFO models the namespace is returned as non-authoritative
    so that the domain validator does not reject unknown-but-possibly-valid
    labels. UFO parsing is a separate, later capability.
    """

    model = workflow.model
    name = model.name.strip().lower()

    if (
        model.source == ModelSource.BUILTIN
        and name in _KNOWN_BUILTIN_SM_NAMES
    ):
        return ModelNamespace(
            model_name=model.name,
            labels=_SM_LABELS,
            authoritative=True,
        )

    # Installed UFO, user UFO, or an unrecognised built-in name: we do not
    # know the full namespace, so we make no membership claims.
    return ModelNamespace(
        model_name=model.name,
        labels=frozenset(),
        authoritative=False,
    )


def _suggest_replacements(
    token: str,
    labels: frozenset[str],
) -> list[str]:
    """Suggest valid label(s) for an unknown token.

    The primary heuristic targets the common failure of gluing two particles
    into one token (``tt~`` -> ``t`` ``t~``, ``e+e-`` -> ``e+`` ``e-``). If the
    token splits cleanly into two known labels, those are returned in order.
    Otherwise labels sharing the token's alphabetic stem are offered.
    """

    cleaned = token.strip().lower()

    # Two-way split into known labels.
    best_split: list[str] | None = None
    for index in range(1, len(cleaned)):
        left = cleaned[:index]
        right = cleaned[index:]
        if left in labels and right in labels:
            candidate = [left, right]
            # Prefer the split whose parts are longest/most specific.
            if best_split is None or (
                min(len(left), len(right))
                > min(len(best_split[0]), len(best_split[1]))
            ):
                best_split = candidate

    if best_split is not None:
        return best_split

    # Fall back to same-stem labels (strip charge/conjugation markers).
    stem = cleaned.rstrip("+-~")
    stem_matches = sorted(
        label
        for label in labels
        if label.rstrip("+-~") == stem and label != cleaned
    )

    return stem_matches


def _iter_process_tokens(
    workflow: WorkflowIntent,
):
    """Yield ``(token, path)`` for every particle label in the workflow."""

    for process_index, process in enumerate(workflow.processes):
        base = f"processes[{process_index}]"

        for index, name in enumerate(process.incoming_particles):
            yield name, f"{base}.incoming_particles[{index}]"

        for index, node in enumerate(process.final_particles):
            for nested in node.walk():
                yield nested.particle, f"{base}.final_particles[{index}]"

        for index, name in enumerate(process.required_intermediates):
            yield name, f"{base}.required_intermediates[{index}]"

        for index, name in enumerate(process.excluded_particles):
            yield name, f"{base}.excluded_particles[{index}]"


def validate_model_domain(
    workflow: WorkflowIntent,
) -> ValidationReport:
    """Reject particle tokens that do not exist in the selected model.

    Returns an empty (passing) report whenever the model namespace is not
    authoritatively known, so custom-model and future-model workflows are never
    falsely blocked.
    """

    namespace = namespace_for_model(workflow)

    if not namespace.authoritative:
        return ValidationReport(issues=())

    issues: list[ValidationIssue] = []
    seen: set[tuple[str, str]] = set()

    for token, path in _iter_process_tokens(workflow):
        if namespace.contains(token):
            continue

        key = (token.strip().lower(), path)
        if key in seen:
            continue
        seen.add(key)

        suggestions = _suggest_replacements(token, namespace.labels)

        if suggestions:
            hint = " Did you mean: " + ", ".join(
                repr(item) for item in suggestions
            ) + "?"
        else:
            hint = ""

        issues.append(
            ValidationIssue(
                code="unknown_model_particle",
                message=(
                    f"The token {token!r} is not a particle or multiparticle "
                    f"defined in the selected model {namespace.model_name!r}."
                    + hint
                ),
                level=ValidationLevel.ERROR,
                path=path,
            )
        )

    return ValidationReport(issues=tuple(issues))
