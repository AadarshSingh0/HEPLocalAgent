"""Configuration models for local-agent routing profiles."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class AgentProfile(BaseModel):
    """Models and limits used by one agent experiment."""

    model_config = ConfigDict(extra="forbid")

    primary_model: str = Field(min_length=1)
    fallback_model: str | None = None

    primary_timeout_seconds: int = Field(gt=0)
    fallback_timeout_seconds: int | None = Field(default=None, gt=0)

    max_repairs: int = Field(default=2, ge=0)
    max_planner_attempts: int = Field(default=2, ge=1, le=5)

    @property
    def has_fallback(self) -> bool:
        return self.fallback_model is not None


def load_agent_profiles(
    path: str | Path,
) -> dict[str, AgentProfile]:
    """Load and validate named agent profiles from JSON."""

    config_path = Path(path)

    with config_path.open("r", encoding="utf-8") as handle:
        raw_profiles = json.load(handle)

    if not isinstance(raw_profiles, dict):
        raise ValueError("Agent profile configuration must be an object.")

    return {
        name: AgentProfile.model_validate(profile)
        for name, profile in raw_profiles.items()
    }
