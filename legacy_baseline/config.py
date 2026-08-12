"""Portable runtime configuration for the retained legacy baseline."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_PATHS_FILE = PROJECT_ROOT / "configs" / "local_paths.json"


def _load_local_paths(config_path: Path) -> dict[str, str]:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in payload.items()
        if isinstance(value, str) and value.strip()
    }


def resolve_executable(
    *,
    environment_variable: str,
    config_key: str,
    candidates: tuple[str, ...],
    config_path: Path = LOCAL_PATHS_FILE,
) -> str:
    """Resolve an executable from environment, local config, or ``PATH``."""

    override = os.environ.get(environment_variable, "").strip()
    if override:
        return str(Path(override).expanduser())

    configured = _load_local_paths(config_path).get(config_key, "").strip()
    if configured:
        return str(Path(configured).expanduser())

    for candidate in candidates:
        discovered = shutil.which(candidate)
        if discovered:
            return discovered

    # Keep the legacy subprocess behavior while allowing a later PATH lookup.
    return candidates[0]


MG5_PATH = resolve_executable(
    environment_variable="HEP_AGENT_MG5_EXECUTABLE",
    config_key="mg5_executable",
    candidates=("mg5_aMC", "mg5"),
)
MA5_PATH = resolve_executable(
    environment_variable="HEP_AGENT_MADANALYSIS5_EXECUTABLE",
    config_key="madanalysis5_executable",
    candidates=("ma5",),
)

DEFAULT_OLLAMA_HOST = (
    os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
).rstrip("/")
DEFAULT_OPENAI_BASE_URL = (
    os.environ.get("OPENAI_BASE_URL") or f"{DEFAULT_OLLAMA_HOST}/v1"
).rstrip("/")

DEFAULT_OUTPUT_DIR = "output"
DEFAULT_LOG_DIR = "logs"
