"""Validation of externally executed HEP workflow outcomes."""

from __future__ import annotations

from hep_agent.execution.madgraph_runner import (
    MadGraphExecutionResult,
)
from hep_agent.execution.result_parser import (
    MadGraphPhysicsResult,
)


OUTPUT_VALIDATION_FAILURE = (
    "execution_output_validation_failure"
)


def execution_has_valid_physics_output(
    execution: MadGraphExecutionResult,
    physics: MadGraphPhysicsResult | None,
) -> bool:
    """Whether execution produced a validated physics result.

    A zero subprocess return code is not sufficient. The result parser
    must also recover the expected MadGraph physics summary.
    """

    return bool(
        execution.success
        and physics is not None
        and physics.has_physics_summary
    )
