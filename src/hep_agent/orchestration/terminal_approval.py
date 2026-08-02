"""Terminal approval interface for collider-agent execution."""

from __future__ import annotations

import select
import sys
import time
from collections.abc import Callable
from typing import TextIO

from hep_agent.orchestration.approval import (
    ApprovalDecision,
    ApprovalResult,
)


TimedReader = Callable[[float], str | None]
InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]


def read_terminal_line(
    timeout_seconds: float,
    *,
    input_stream: TextIO = sys.stdin,
) -> str | None:
    """Read one terminal line within a timeout.

    Returns None when the user provides no input.
    """

    if timeout_seconds < 0:
        raise ValueError("timeout_seconds cannot be negative.")

    if not input_stream.isatty():
        time.sleep(timeout_seconds)
        return None

    readable, _, _ = select.select(
        [input_stream],
        [],
        [],
        timeout_seconds,
    )

    if not readable:
        return None

    return input_stream.readline().strip()


def resolve_terminal_approval(
    approval: ApprovalResult,
    *,
    timed_reader: TimedReader = read_terminal_line,
    input_function: InputFunction = input,
    output_function: OutputFunction = print,
) -> bool:
    """Resolve one approval decision in a terminal.

    Returns True when execution is approved and False when it is
    cancelled.
    """

    output_function("")
    output_function("=== EXECUTION APPROVAL ===")

    for reason in approval.reasons:
        output_function(f"Reason: {reason}")

    if approval.decision == ApprovalDecision.BLOCKED:
        output_function("Execution is blocked.")
        return False

    if approval.decision == ApprovalDecision.EXPLICIT_CONFIRMATION:
        output_function(
            "This workflow requires explicit confirmation."
        )

        while True:
            answer = input_function(
                "Type YES to execute or NO to cancel: "
            ).strip().lower()

            if answer in {"yes", "y"}:
                output_function("Execution approved.")
                return True

            if answer in {"no", "n", "cancel", "c", "edit", "e"}:
                output_function("Execution cancelled.")
                return False

            output_function(
                "Please enter YES or NO."
            )

    delay = approval.auto_confirm_delay_seconds or 0

    if delay == 0:
        output_function("Execution automatically approved.")
        return True

    output_function(
        "The workflow passed all automatic checks."
    )
    output_function(
        "Type c and press Enter to cancel, or e to edit."
    )

    for remaining in range(delay, 0, -1):
        output_function(
            f"Auto-executing in {remaining} second"
            f"{'s' if remaining != 1 else ''}..."
        )

        action = timed_reader(1.0)

        if action is None:
            continue

        normalized = action.strip().lower()

        if normalized in {
            "c",
            "cancel",
            "n",
            "no",
            "e",
            "edit",
        }:
            output_function("Execution cancelled.")
            return False

        if normalized in {"y", "yes", "run", "execute"}:
            output_function("Execution approved immediately.")
            return True

        output_function(
            f"Input {action!r} was not recognised; "
            "countdown continues."
        )

    output_function("No cancellation received. Executing now.")
    return True
