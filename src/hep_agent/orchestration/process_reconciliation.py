"""Deterministic reconciliation of inclusive and partonic processes.

For MadGraph, an inclusive hadron-level process such as

    p p > e+ e-

already expands the proton multiparticle definitions into the allowed
partonic subprocesses. Explicit partonic processes with the same
process body must therefore not be added alongside it.

This module changes no final states, cuts, coupling constraints,
decays, or model settings. It only removes narrower incoming-state
processes that are already covered by an inclusive collider-beam
process with an otherwise identical specification.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from hep_agent.schemas import WorkflowIntent


@dataclass(frozen=True)
class ProcessReconciliationResult:
    """Result of deterministic inclusive-process reconciliation."""

    workflow: WorkflowIntent
    removed_process_ids: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.removed_process_ids)


def _process_body_signature(
    process: object,
) -> str:
    """Describe a process while excluding ID and incoming state."""

    payload = process.model_dump(
        mode="json"
    )

    payload.pop("process_id", None)
    payload.pop(
        "incoming_particles",
        None,
    )

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def remove_redundant_inclusive_subprocesses(
    workflow: WorkflowIntent,
) -> ProcessReconciliationResult:
    """Remove explicit subprocesses covered by an inclusive process.

    A process is considered inclusive when its incoming particles are
    exactly the configured collider beams.

    A narrower process is removed only when:

    - an inclusive process exists;
    - the final-state/process specification is otherwise identical;
    - only the process ID and incoming particles differ.

    Distinct final states, decay trees, exclusions, intermediate
    particles, and coupling constraints are preserved.
    """

    beam_particles = tuple(
        beam.particle
        for beam in workflow.collider.beams
    )

    inclusive_signatures = {
        _process_body_signature(process)
        for process in workflow.processes
        if tuple(
            process.incoming_particles
        ) == beam_particles
    }

    if not inclusive_signatures:
        return ProcessReconciliationResult(
            workflow=workflow
        )

    kept_processes = []
    removed_ids: list[str] = []

    for process in workflow.processes:
        incoming = tuple(
            process.incoming_particles
        )
        signature = _process_body_signature(
            process
        )

        covered_by_inclusive = (
            incoming != beam_particles
            and signature
            in inclusive_signatures
        )

        if covered_by_inclusive:
            removed_ids.append(
                process.process_id
            )
            continue

        kept_processes.append(process)

    if not removed_ids:
        return ProcessReconciliationResult(
            workflow=workflow
        )

    note = (
        "Deterministically removed explicit subprocesses already "
        "covered by an inclusive collider-beam process: "
        + ", ".join(removed_ids)
        + "."
    )

    notes = list(workflow.notes)

    if note not in notes:
        notes.append(note)

    corrected = workflow.model_copy(
        update={
            "processes": kept_processes,
            "notes": notes,
        },
        deep=True,
    )

    return ProcessReconciliationResult(
        workflow=corrected,
        removed_process_ids=tuple(
            removed_ids
        ),
    )
