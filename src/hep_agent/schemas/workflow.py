"""Structured collider-workflow schema.

This module defines the internal language shared by the LLM planner,
deterministic builders, validators, and execution controller.

The schema describes physics intent. It does not contain unrestricted
MadGraph command strings.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterator

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hep_agent.schemas.analysis import AnalysisPlan


class StrictModel(BaseModel):
    """Base class that rejects unknown fields."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class TaskType(str, Enum):
    GENERATE_PROCESS = "generate_process"
    RUN_SIMULATION = "run_simulation"
    REPAIR_FAILED_RUN = "repair_failed_run"
    ANALYSE_EXISTING_OUTPUT = "analyse_existing_output"
    PATCH_PARAMETER_CARD = "patch_parameter_card"
    PLAN_PARAMETER_SCAN = "plan_parameter_scan"


class ColliderType(str, Enum):
    HADRON = "hadron"
    LEPTON = "lepton"
    PARTONIC = "partonic"
    UNKNOWN = "unknown"


class EnergyMeaning(str, Enum):
    TOTAL_CENTER_OF_MASS = "total_center_of_mass"
    PER_BEAM = "per_beam"


class ModelSource(str, Enum):
    BUILTIN = "builtin"
    INSTALLED_UFO = "installed_ufo"
    USER_UFO = "user_ufo"


class FieldSource(str, Enum):
    USER = "user"
    VALIDATED_DEFAULT = "validated_default"
    MODEL_INFERENCE = "model_inference"
    REPAIR = "repair"
    FALLBACK_REVIEW = "fallback_review"


class CouplingComparison(str, Enum):
    EXACT = "exact"
    MAXIMUM = "maximum"
    MINIMUM = "minimum"


class BeamSpec(StrictModel):
    """One physical collider beam."""

    particle: str = Field(min_length=1)
    label: str | None = None


class EnergySpec(StrictModel):
    """Collider energy and its interpretation."""

    value_gev: float = Field(gt=0)
    meaning: EnergyMeaning


class ColliderSpec(StrictModel):
    """Physical accelerator configuration."""

    collider_type: ColliderType
    beams: list[BeamSpec] = Field(min_length=2, max_length=2)
    energy: EnergySpec


class PhysicsModelSpec(StrictModel):
    """Physics model requested for the workflow."""

    name: str = Field(min_length=1)
    source: ModelSource = ModelSource.BUILTIN
    model_path: str | None = None

    @model_validator(mode="after")
    def require_path_for_user_ufo(self) -> "PhysicsModelSpec":
        if self.source == ModelSource.USER_UFO and not self.model_path:
            raise ValueError("A user UFO model requires model_path.")
        return self


class CouplingOrderSpec(StrictModel):
    """Structured coupling-order restriction."""

    value: int = Field(ge=0)
    comparison: CouplingComparison = CouplingComparison.MAXIMUM


class ParticleNode(StrictModel):
    """A produced particle with an optional recursive decay tree."""

    particle: str = Field(min_length=1)
    branch_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z][A-Za-z0-9_]*$",
    )
    label: str | None = None
    decay_products: list["ParticleNode"] = Field(default_factory=list)

    def walk(self) -> Iterator["ParticleNode"]:
        """Visit this particle and every particle below it."""

        yield self
        for child in self.decay_products:
            yield from child.walk()


class ProcessSpec(StrictModel):
    """One hard process and its decay structure."""

    process_id: str = Field(
        default="process_1",
        pattern=r"^[A-Za-z][A-Za-z0-9_]*$",
    )
    incoming_particles: list[str] = Field(min_length=1)
    final_particles: list[ParticleNode] = Field(min_length=1)

    required_intermediates: list[str] = Field(default_factory=list)
    excluded_particles: list[str] = Field(default_factory=list)
    coupling_orders: dict[str, CouplingOrderSpec] = Field(default_factory=dict)

    @field_validator("incoming_particles")
    @classmethod
    def reject_blank_incoming_particles(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("Incoming particle names cannot be blank.")
        return values

    @model_validator(mode="after")
    def require_unique_branch_ids(self) -> "ProcessSpec":
        branch_ids = [
            node.branch_id
            for particle in self.final_particles
            for node in particle.walk()
            if node.branch_id is not None
        ]

        if len(branch_ids) != len(set(branch_ids)):
            raise ValueError(
                f"Duplicate branch_id values found in {self.process_id}."
            )

        return self


class RunSettings(StrictModel):
    """Settings controlling event generation and execution."""

    nevents: int = Field(default=10_000, gt=0)
    random_seed: int | None = Field(default=None, ge=0)
    timeout_seconds: int = Field(default=1800, gt=0)
    output_name: str | None = None


class PipelineSpec(StrictModel):
    """Requested collider-tool stages."""

    madgraph: bool = True
    pythia8: bool = False
    delphes: bool = False
    madanalysis: bool = False


class WorkflowIntent(StrictModel):
    """Complete structured collider request."""

    schema_version: str = "1.0"
    task_type: TaskType

    model: PhysicsModelSpec
    collider: ColliderSpec
    processes: list[ProcessSpec] = Field(min_length=1)

    run: RunSettings = Field(default_factory=RunSettings)
    pipeline: PipelineSpec = Field(default_factory=PipelineSpec)

    # None preserves the existing deterministic quick-look preset.
    # A populated plan requests custom structured MA5 analysis.
    analysis: AnalysisPlan | None = None

    field_sources: dict[str, FieldSource] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_complete_workflow(self) -> "WorkflowIntent":
        """Validate process IDs and analysis-pipeline consistency."""

        process_ids = [
            process.process_id
            for process in self.processes
        ]

        if len(process_ids) != len(
            set(process_ids)
        ):
            raise ValueError(
                "Every process_id must be unique."
            )

        if (
            self.analysis is not None
            and not self.pipeline.madanalysis
        ):
            raise ValueError(
                "A structured analysis plan requires "
                "pipeline.madanalysis=true."
            )

        return self


ParticleNode.model_rebuild()
WorkflowIntent.model_rebuild()
