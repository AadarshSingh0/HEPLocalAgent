"""Runtime isolation for managed MadAnalysis 5 executions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


RUNTIME_METADATA_SUFFIX = ".runtime.json"

_CONFLICTING_VARIABLES = {
    "DYLD_FALLBACK_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
    "LD_LIBRARY_PATH",
    "LIBRARY_PATH",
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHIA8DATA",
    "ROOT_INCLUDE_PATH",
    "ROOTSYS",
    "VIRTUAL_ENV",
}

_SYSTEM_PATHS = (
    "/usr/local/sbin",
    "/usr/local/bin",
    "/usr/sbin",
    "/usr/bin",
    "/sbin",
    "/bin",
)


class MadAnalysisRuntimeConfigurationError(ValueError):
    """Raised when managed MA5 runtime metadata is stale or invalid."""


@dataclass(frozen=True)
class MadAnalysisRuntime:
    """Pinned executables and ROOT paths for one managed MA5 launcher."""

    python_executable: Path
    native_executable: Path
    root_config: Path
    root_prefix: Path
    root_bindir: Path
    root_libdir: Path
    platform: str


def runtime_metadata_path(executable: str | Path) -> Path:
    """Return the sidecar path for a managed MA5 launcher."""

    path = Path(executable).expanduser().resolve()
    return path.with_name(path.name + RUNTIME_METADATA_SUFFIX)


def _required_absolute_path(
    payload: Mapping[str, object],
    key: str,
) -> Path:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MadAnalysisRuntimeConfigurationError(
            f"MadAnalysis runtime metadata is missing {key!r}."
        )

    path = Path(value).expanduser()
    if not path.is_absolute():
        raise MadAnalysisRuntimeConfigurationError(
            f"MadAnalysis runtime metadata path {key!r} must be absolute."
        )
    return path.absolute()


def load_madanalysis_runtime(
    executable: str | Path,
) -> MadAnalysisRuntime | None:
    """Load and validate optional managed-runtime metadata."""

    metadata_path = runtime_metadata_path(executable)
    if not metadata_path.is_file():
        return None

    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MadAnalysisRuntimeConfigurationError(
            f"Could not read MadAnalysis runtime metadata "
            f"{metadata_path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise MadAnalysisRuntimeConfigurationError(
            "MadAnalysis runtime metadata must be a JSON object."
        )

    platform = payload.get("platform")
    if platform not in {"Linux", "Darwin"}:
        raise MadAnalysisRuntimeConfigurationError(
            "MadAnalysis runtime metadata has an unsupported platform."
        )

    runtime = MadAnalysisRuntime(
        python_executable=_required_absolute_path(
            payload,
            "python_executable",
        ),
        native_executable=_required_absolute_path(
            payload,
            "native_executable",
        ),
        root_config=_required_absolute_path(payload, "root_config"),
        root_prefix=_required_absolute_path(payload, "root_prefix"),
        root_bindir=_required_absolute_path(payload, "root_bindir"),
        root_libdir=_required_absolute_path(payload, "root_libdir"),
        platform=platform,
    )

    for label, path in (
        ("Python executable", runtime.python_executable),
        ("native MA5 executable", runtime.native_executable),
        ("root-config", runtime.root_config),
    ):
        if not path.is_file() or not os.access(path, os.X_OK):
            raise MadAnalysisRuntimeConfigurationError(
                f"Pinned {label} is not runnable: {path}. "
                "Rerun the installer from the current clone."
            )
    current_python = Path(sys.executable).absolute()
    if runtime.python_executable != current_python:
        raise MadAnalysisRuntimeConfigurationError(
            "Pinned Python belongs to a different repository clone: "
            f"{runtime.python_executable}. Current clone Python is "
            f"{current_python}. Rerun the installer from the current "
            "clone to regenerate the managed launcher."
        )

    for label, path in (
        ("ROOT prefix", runtime.root_prefix),
        ("ROOT binary directory", runtime.root_bindir),
        ("ROOT library directory", runtime.root_libdir),
    ):
        if not path.is_dir():
            raise MadAnalysisRuntimeConfigurationError(
                f"Pinned {label} does not exist: {path}. "
                "Rerun the installer to select a compatible ROOT runtime."
            )

    return runtime


def _remove_conflicting_variables(environment: dict[str, str]) -> None:
    for variable in tuple(environment):
        if (
            variable in _CONFLICTING_VARIABLES
            or variable.startswith("CONDA_")
            or variable.startswith("_CE_")
        ):
            environment.pop(variable, None)


def build_madanalysis_environment(
    executable: str | Path,
    *,
    inherited: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Construct a small, deterministic environment for an MA5 process.

    Managed launchers have a JSON sidecar written by the installer. Its
    current-clone Python and selected ROOT paths replace every conflicting
    shell value. Unmanaged executables still receive a clean Python/runtime
    environment, but no ROOT installation is guessed from the inherited PATH.
    """

    environment = dict(os.environ if inherited is None else inherited)
    _remove_conflicting_variables(environment)

    executable_path = Path(executable).expanduser().resolve()
    runtime = load_madanalysis_runtime(executable_path)

    if runtime is None:
        python_bindir = Path(sys.executable).resolve().parent
        search_path = (
            python_bindir,
            executable_path.parent,
            *(Path(value) for value in _SYSTEM_PATHS),
        )
        environment["VIRTUAL_ENV"] = str(python_bindir.parent)
    else:
        python_bindir = runtime.python_executable.parent
        search_path = (
            runtime.root_bindir,
            python_bindir,
            executable_path.parent,
            *(Path(value) for value in _SYSTEM_PATHS),
        )
        environment["VIRTUAL_ENV"] = str(python_bindir.parent)
        environment["ROOTSYS"] = str(runtime.root_prefix)
        if runtime.platform == "Linux":
            environment["LD_LIBRARY_PATH"] = str(runtime.root_libdir)

    environment["PATH"] = os.pathsep.join(
        dict.fromkeys(str(path) for path in search_path)
    )
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def verify_root_metadata(runtime: MadAnalysisRuntime) -> None:
    """Ensure root-config still reports the paths recorded by the installer."""

    expected = {
        "--prefix": runtime.root_prefix,
        "--bindir": runtime.root_bindir,
        "--libdir": runtime.root_libdir,
    }
    environment = build_madanalysis_environment(
        runtime.native_executable,
        inherited={},
    )

    for option, expected_path in expected.items():
        completed = subprocess.run(
            [str(runtime.root_config), option],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        actual = completed.stdout.strip()
        if completed.returncode != 0 or not actual:
            raise MadAnalysisRuntimeConfigurationError(
                f"Pinned root-config could not report {option}."
            )
        if Path(actual).expanduser().resolve() != expected_path:
            raise MadAnalysisRuntimeConfigurationError(
                "Pinned ROOT metadata no longer matches root-config: "
                f"{option} reported {actual!r}, expected "
                f"{str(expected_path)!r}. Rerun the installer."
            )
