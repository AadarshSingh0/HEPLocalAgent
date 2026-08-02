"""Safe structural normalization of model-produced workflow JSON.

This module repairs representation-level problems before strict
WorkflowIntent validation. It does not infer or change physics.

Currently supported repairs:

- remove exact duplicate process objects;
- assign deterministic unique IDs to missing or duplicate process IDs.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any


_PROCESS_ID_PATTERN = re.compile(
    r"^[A-Za-z][A-Za-z0-9_-]*$"
)


def _process_signature(
    process: dict[str, Any],
) -> str:
    """Create a canonical process signature excluding its identifier."""

    content = {
        key: value
        for key, value in process.items()
        if key != "process_id"
    }

    return json.dumps(
        content,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _next_process_id(
    *,
    position: int,
    used_ids: set[str],
) -> str:
    """Return a deterministic unused process identifier."""

    counter = position

    while True:
        candidate = f"process_{counter:03d}"

        if candidate not in used_ids:
            return candidate

        counter += 1


def sanitize_workflow_payload(
    payload: Any,
) -> Any:
    """Normalize safe structural defects in a workflow payload.

    Non-dictionary payloads and payloads without a process list are
    returned unchanged.
    """

    if not isinstance(payload, dict):
        return payload

    processes = payload.get("processes")

    if not isinstance(processes, list):
        return payload

    sanitized_payload = copy.deepcopy(payload)

    sanitized_processes: list[Any] = []
    seen_signatures: set[str] = set()
    used_ids: set[str] = set()

    for raw_process in processes:
        if not isinstance(raw_process, dict):
            sanitized_processes.append(
                copy.deepcopy(raw_process)
            )
            continue

        process = copy.deepcopy(raw_process)
        signature = _process_signature(process)

        # Keeping the same physical process twice could duplicate an
        # MG5 contribution. Exact redundant copies are therefore
        # removed rather than merely renamed.
        if signature in seen_signatures:
            continue

        seen_signatures.add(signature)

        raw_id = process.get("process_id")

        valid_id = (
            isinstance(raw_id, str)
            and bool(
                _PROCESS_ID_PATTERN.fullmatch(
                    raw_id.strip()
                )
            )
        )

        candidate = (
            raw_id.strip()
            if valid_id
            else ""
        )

        if (
            not candidate
            or candidate in used_ids
        ):
            candidate = _next_process_id(
                position=(
                    len(sanitized_processes)
                    + 1
                ),
                used_ids=used_ids,
            )

        process["process_id"] = candidate
        used_ids.add(candidate)
        sanitized_processes.append(process)

    sanitized_payload["processes"] = (
        sanitized_processes
    )

    return sanitized_payload


def sanitize_workflow_json(
    raw_json: str,
) -> str:
    """Normalize valid JSON while preserving malformed input handling.

    Malformed JSON is returned unchanged so Pydantic's existing
    validation path still produces the original JSON error.
    """

    if not isinstance(raw_json, str):
        return raw_json

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return raw_json

    sanitized = sanitize_workflow_payload(
        payload
    )

    if sanitized == payload:
        return raw_json

    return json.dumps(
        sanitized,
        ensure_ascii=False,
        separators=(",", ":"),
    )
