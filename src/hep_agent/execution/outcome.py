"""Validation of externally executed HEP workflow outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hep_agent.execution.madgraph_runner import (
    MadGraphExecutionResult,
)
from hep_agent.execution.result_parser import (
    MadGraphPhysicsResult,
)


OUTPUT_VALIDATION_FAILURE = (
    "execution_output_validation_failure"
)

PARTON_LEVEL_LHE_OUTPUT = "parton_level_lhe"
SHOWERED_HEPMC_OUTPUT = "showered_hepmc"
DETECTOR_ROOT_OUTPUT = "detector_root"


@dataclass(frozen=True)
class ExecutionOutputValidation:
    """Result of checking subprocess, summary, and requested artifacts."""

    is_valid: bool
    missing_requested_outputs: tuple[str, ...] = ()


def _is_file(path: str | Path | None) -> bool:
    """Whether one discovered output path still names a regular file."""

    return path is not None and Path(path).is_file()


def validate_execution_outputs(
    execution: MadGraphExecutionResult,
    physics: MadGraphPhysicsResult | None,
    *,
    require_lhe: bool = True,
    require_hepmc: bool = False,
    require_root: bool = False,
) -> ExecutionOutputValidation:
    """Validate normal-run success against the requested pipeline stages.

    A successful event-generation workflow always requires a parton-level
    LHE file. Later-stage artifacts are required only when the corresponding
    Pythia8 or Delphes stage was requested.
    """

    missing: list[str] = []

    if require_lhe and not _is_file(
        (
            physics.primary_lhe_file
            if physics is not None
            else None
        )
    ):
        missing.append(PARTON_LEVEL_LHE_OUTPUT)

    if require_hepmc and not _is_file(
        (
            physics.showered_hepmc_file
            if physics is not None
            else None
        )
    ):
        missing.append(SHOWERED_HEPMC_OUTPUT)

    if require_root and not _is_file(
        (
            physics.detector_root_file
            if physics is not None
            else None
        )
    ):
        missing.append(DETECTOR_ROOT_OUTPUT)

    valid = bool(
        execution.success
        and physics is not None
        and physics.has_physics_summary
        and not missing
    )

    return ExecutionOutputValidation(
        is_valid=valid,
        missing_requested_outputs=tuple(missing),
    )


def execution_has_valid_physics_output(
    execution: MadGraphExecutionResult,
    physics: MadGraphPhysicsResult | None,
    *,
    require_lhe: bool = True,
    require_hepmc: bool = False,
    require_root: bool = False,
) -> bool:
    """Whether execution produced every required physics output.

    A zero subprocess return code is not sufficient. The result parser
    must recover the expected MadGraph physics summary and every artifact
    requested by the pipeline.
    """

    return validate_execution_outputs(
        execution,
        physics,
        require_lhe=require_lhe,
        require_hepmc=require_hepmc,
        require_root=require_root,
    ).is_valid
