"""Prepare natural-language energy scans without executing HEP tools.

The ordinary workflow planner is called exactly once to construct and
validate the base collider workflow. The extracted energy range is then
expanded deterministically without further LLM calls.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from hep_agent.models import (
    AgentProfile,
    OllamaClient,
)
from hep_agent.orchestration.preexecution import (
    PreExecutionResult,
    run_preexecution_loop,
)
from hep_agent.scans.energy_scan import (
    EnergyScanPlan,
    EnergyScanRequest,
    ExpandedEnergyScan,
    build_energy_scan_plan_from_range,
    expand_energy_scan,
)
from hep_agent.scans.text_parser import (
    ParsedEnergyScanText,
    parse_energy_scan_text,
)


@dataclass(frozen=True)
class PreparedEnergyScan:
    """One natural-language energy scan prepared for approval."""

    original_request: str
    parsed_text: ParsedEnergyScanText
    base_result: PreExecutionResult

    plan: EnergyScanPlan | None = None
    expanded: ExpandedEnergyScan | None = None

    preparation_wall_time_seconds: float = 0.0

    @property
    def is_ready(self) -> bool:
        """Whether the complete scan can be displayed for approval."""

        return bool(
            self.base_result.is_ready
            and self.plan is not None
            and self.expanded is not None
        )

    @property
    def point_count(self) -> int:
        """Number of points in the prepared scan."""

        if self.expanded is None:
            return 0

        return self.expanded.point_count

    @property
    def total_requested_events(self) -> int:
        """Total events requested over all scan points."""

        if self.expanded is None:
            return 0

        return self.expanded.total_requested_events

    @property
    def failure_message(self) -> str | None:
        """Human-readable preparation failure."""

        if self.is_ready:
            return None

        return (
            self.base_result.failure_message
            or "The base collider workflow was not ready."
        )


def prepare_energy_scan(
    user_request: str,
    *,
    client: OllamaClient,
    profile: AgentProfile,
) -> PreparedEnergyScan | None:
    """Prepare an energy scan or return ``None`` for an ordinary request.

    The language model is used only for the base workflow. Numerical
    scan points, seeds, and output names are generated deterministically.
    """

    started = time.perf_counter()

    parsed = parse_energy_scan_text(
        user_request
    )

    if parsed is None:
        return None

    base_result = run_preexecution_loop(
        parsed.base_request,
        client=client,
        profile=profile,
    )

    elapsed = time.perf_counter() - started

    if not base_result.is_ready:
        return PreparedEnergyScan(
            original_request=parsed.original_request,
            parsed_text=parsed,
            base_result=base_result,
            preparation_wall_time_seconds=elapsed,
        )

    if base_result.workflow is None:
        raise RuntimeError(
            "A ready base workflow result does not contain "
            "a WorkflowIntent."
        )

    request = EnergyScanRequest(
        base_workflow=base_result.workflow,
        energy_range=parsed.energy_range,
        continue_on_failure=True,
    )

    plan = build_energy_scan_plan_from_range(
        request
    )

    expanded = expand_energy_scan(
        plan
    )

    return PreparedEnergyScan(
        original_request=parsed.original_request,
        parsed_text=parsed,
        base_result=base_result,
        plan=plan,
        expanded=expanded,
        preparation_wall_time_seconds=elapsed,
    )
