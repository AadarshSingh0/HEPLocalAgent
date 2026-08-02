"""Public imports for external execution and result parsing."""

from .madgraph_runner import (
    ExecutionFailureCategory,
    MadGraphExecutionResult,
    run_madgraph_workflow,
)
from .result_parser import (
    MadGraphPhysicsResult,
    find_detector_root_file,
    find_primary_lhe_file,
    find_showered_hepmc_file,
    parse_madgraph_result,
)

__all__ = [
    "ExecutionFailureCategory",
    "MadGraphExecutionResult",
    "MadGraphPhysicsResult",
    "find_detector_root_file",
    "find_primary_lhe_file",
    "find_showered_hepmc_file",
    "parse_madgraph_result",
    "run_madgraph_workflow",
]
