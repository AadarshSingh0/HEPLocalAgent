"""Environment and installation checks for the HEP agent."""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from hep_agent.doctor.models import (
    CheckStatus,
    DoctorCheck,
    DoctorReport,
)


DEFAULT_PROFILE = "qwen_primary"


def default_project_root() -> Path:
    """Return the local_hep_agent repository root."""

    return Path(__file__).resolve().parents[3]


def _check(
    check_id: str,
    label: str,
    status: CheckStatus,
    summary: str,
    *,
    required: bool = True,
    details: dict[str, Any] | None = None,
    remediation: str | None = None,
) -> DoctorCheck:
    return DoctorCheck(
        check_id=check_id,
        label=label,
        status=status,
        summary=summary,
        required=required,
        details=details,
        remediation=remediation,
    )


def _load_json(
    path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError:
        return None, "File does not exist."
    except PermissionError:
        return None, "File is not readable."
    except json.JSONDecodeError as exc:
        return None, (
            "Invalid JSON at "
            f"line {exc.lineno}, column {exc.colno}: "
            f"{exc.msg}"
        )

    if not isinstance(payload, dict):
        return None, "Top-level JSON value must be an object."

    return payload, None


def _discover_paths_config(
    project_root: Path,
) -> Path | None:
    configs = project_root / "configs"

    preferred = (
        configs / "local_paths.json",
        configs / "paths.json",
        configs / "tool_paths.json",
    )

    for candidate in preferred:
        if candidate.is_file():
            return candidate

    if not configs.is_dir():
        return None

    for candidate in sorted(
        configs.glob("*.json")
    ):
        payload, error = _load_json(candidate)

        if error or payload is None:
            continue

        if any(
            key.endswith("_executable")
            or key.endswith("_path")
            for key in payload
        ):
            return candidate

    return None


def _normalise_path(
    value: object,
) -> Path | None:
    if not isinstance(value, str):
        return None

    stripped = value.strip()

    if not stripped:
        return None

    return Path(
        os.path.expandvars(stripped)
    ).expanduser()


def _check_executable(
    *,
    check_id: str,
    label: str,
    path: Path | None,
    required: bool,
    remediation: str,
) -> DoctorCheck:
    if path is None:
        return _check(
            check_id,
            label,
            (
                CheckStatus.FAILURE
                if required
                else CheckStatus.WARNING
            ),
            "No executable path is configured.",
            required=required,
            remediation=remediation,
        )

    if not path.exists():
        return _check(
            check_id,
            label,
            (
                CheckStatus.FAILURE
                if required
                else CheckStatus.WARNING
            ),
            "Configured path does not exist.",
            required=required,
            details={"path": str(path)},
            remediation=remediation,
        )

    if not path.is_file():
        return _check(
            check_id,
            label,
            (
                CheckStatus.FAILURE
                if required
                else CheckStatus.WARNING
            ),
            "Configured path is not a regular file.",
            required=required,
            details={"path": str(path)},
            remediation=remediation,
        )

    executable = os.access(
        path,
        os.X_OK,
    )

    if not executable:
        return _check(
            check_id,
            label,
            (
                CheckStatus.FAILURE
                if required
                else CheckStatus.WARNING
            ),
            "Configured file is not executable.",
            required=required,
            details={"path": str(path)},
            remediation=(
                f"Make it executable with: chmod +x {path}"
            ),
        )

    return _check(
        check_id,
        label,
        CheckStatus.PASS,
        "Executable is present and runnable.",
        required=required,
        details={"path": str(path)},
    )


def _check_writable_directory(
    path: Path,
    *,
    check_id: str,
    label: str,
) -> DoctorCheck:
    try:
        path.mkdir(
            parents=True,
            exist_ok=True,
        )

        with tempfile.NamedTemporaryFile(
            prefix=".hep_agent_doctor_",
            dir=path,
            delete=True,
        ):
            pass

    except OSError as exc:
        return _check(
            check_id,
            label,
            CheckStatus.FAILURE,
            "Directory is not writable.",
            details={
                "path": str(path),
                "error": str(exc),
            },
            remediation=(
                "Correct the directory ownership or permissions."
            ),
        )

    return _check(
        check_id,
        label,
        CheckStatus.PASS,
        "Directory exists and is writable.",
        details={"path": str(path)},
    )


def _get_ollama_tags(
    host: str,
    *,
    timeout_seconds: int = 8,
) -> tuple[list[str] | None, str | None]:
    url = f"{host.rstrip('/')}/api/tags"

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            raw = response.read().decode(
                "utf-8"
            )

    except urllib.error.HTTPError as exc:
        return None, (
            f"Ollama returned HTTP {exc.code}."
        )
    except urllib.error.URLError as exc:
        return None, (
            "Could not connect to Ollama: "
            f"{getattr(exc, 'reason', exc)}"
        )
    except TimeoutError:
        return None, "Ollama connection timed out."

    try:
        payload = json.loads(raw)
        models = payload["models"]
    except (
        json.JSONDecodeError,
        KeyError,
        TypeError,
    ):
        return None, (
            "Ollama returned an unexpected /api/tags response."
        )

    names: list[str] = []

    for item in models:
        if not isinstance(item, dict):
            continue

        name = item.get("name")

        if isinstance(name, str):
            names.append(name)

    return sorted(set(names)), None


def _ollama_chat_smoke(
    host: str,
    model: str,
    *,
    timeout_seconds: int,
) -> tuple[str | None, str | None]:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Reply with exactly READY."
                ),
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 8,
        },
    }

    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=json.dumps(
            payload
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            raw = response.read().decode(
                "utf-8"
            )

    except urllib.error.HTTPError as exc:
        return None, (
            f"Ollama returned HTTP {exc.code}."
        )
    except urllib.error.URLError as exc:
        return None, (
            "Could not connect to Ollama: "
            f"{getattr(exc, 'reason', exc)}"
        )
    except TimeoutError:
        return None, "Model smoke test timed out."

    try:
        parsed = json.loads(raw)
        content = parsed["message"]["content"]
    except (
        json.JSONDecodeError,
        KeyError,
        TypeError,
    ):
        return None, (
            "Ollama returned an invalid chat response."
        )

    if not isinstance(content, str):
        return None, (
            "Ollama returned non-text chat content."
        )

    return content.strip(), None


def _mg5_root(
    executable: Path | None,
) -> Path | None:
    if executable is None:
        return None

    try:
        resolved = executable.resolve()
    except OSError:
        resolved = executable

    if resolved.parent.name == "bin":
        return resolved.parent.parent

    return resolved.parent


def _expand_executable_candidates(
    candidates: list[Path],
    executable_names: tuple[str, ...],
) -> list[Path]:
    expanded: list[Path] = []

    for candidate in candidates:
        if candidate.is_file():
            expanded.append(candidate)
            continue

        for executable_name in executable_names:
            expanded.extend(
                [
                    candidate / executable_name,
                    candidate / "bin" / executable_name,
                ]
            )

    return expanded


def _find_first_executable(
    candidates: list[Path],
    executable_names: tuple[str, ...],
) -> tuple[Path | None, list[Path]]:
    expanded = _expand_executable_candidates(
        candidates,
        executable_names,
    )

    for candidate in expanded:
        if (
            candidate.is_file()
            and os.access(candidate, os.X_OK)
        ):
            return candidate, expanded

    return None, expanded


def _pythia_installation_check(
    executable: Path | None,
    searched: list[Path],
) -> DoctorCheck:
    if executable is None:
        return _check(
            "pythia8_installation",
            "Pythia8 installation",
            CheckStatus.WARNING,
            (
                "No runnable pythia8-config executable "
                "was found."
            ),
            required=False,
            details={
                "searched": [
                    str(candidate)
                    for candidate in searched
                ]
            },
            remediation=(
                "Install Pythia8 through MG5 or configure "
                "pythia8_path in the local paths file."
            ),
        )

    prefix = executable.parent.parent
    native_marker = (
        prefix / ".heptoolbench-apple-clang"
    )
    apple_silicon = (
        platform.system() == "Darwin"
        and platform.machine() == "arm64"
    )

    if apple_silicon and not native_marker.is_file():
        return _check(
            "pythia8_installation",
            "Pythia8 installation",
            CheckStatus.WARNING,
            (
                "A runnable Pythia8 executable was found, "
                "but this Apple-Silicon installation has "
                "not passed the native-runtime repair."
            ),
            required=False,
            details={
                "executable": str(executable),
                "missing_marker": str(native_marker),
            },
            remediation=(
                "Rerun ./install.sh --agent-only "
                "--with-pythia8 --yes to rebuild HepMC2 "
                "and Pythia8 with Apple Clang."
            ),
        )

    return _check(
        "pythia8_installation",
        "Pythia8 installation",
        CheckStatus.PASS,
        "A runnable Pythia8 installation was found.",
        required=False,
        details={"executable": str(executable)},
    )


def _delphes_installation_check(
    executable: Path | None,
    searched: list[Path],
) -> DoctorCheck:
    if executable is None:
        return _check(
            "delphes_installation",
            "Delphes installation",
            CheckStatus.WARNING,
            "No runnable Delphes executable was found.",
            required=False,
            details={
                "searched": [
                    str(candidate)
                    for candidate in searched
                ]
            },
            remediation=(
                "Install ROOT and Delphes, or configure "
                "delphes_path in the local paths file."
            ),
        )

    runtime_problem: str | None = None
    try:
        with executable.open("rb") as stream:
            is_elf = stream.read(4) == b"\x7fELF"
    except OSError as error:
        is_elf = False
        runtime_problem = f"Could not inspect executable: {error}"

    if (
        platform.system() == "Linux"
        and executable.name != "DelphesHepMC2"
    ):
        runtime_problem = (
            "MG5's detector workflow requires DelphesHepMC2, "
            f"but only {executable.name} was selected."
        )
    elif platform.system() == "Linux" and is_elf:
        try:
            completed = subprocess.run(
                ["ldd", "-r", str(executable)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            report = "\n".join(
                part
                for part in (
                    completed.stdout.strip(),
                    completed.stderr.strip(),
                )
                if part
            )
            failure_lines = [
                line.strip()
                for line in report.splitlines()
                if (
                    "undefined symbol" in line.lower()
                    or "not found" in line.lower()
                    or "symbol lookup error" in line.lower()
                )
            ]
            if completed.returncode != 0 or failure_lines:
                runtime_problem = (
                    failure_lines[0]
                    if failure_lines
                    else (
                        "Dynamic-link validation returned "
                        f"exit code {completed.returncode}."
                    )
                )
        except (OSError, subprocess.TimeoutExpired) as error:
            runtime_problem = (
                "Could not complete dynamic-link validation: "
                f"{error}"
            )

    if runtime_problem is not None:
        return _check(
            "delphes_installation",
            "Delphes installation",
            CheckStatus.WARNING,
            (
                "DelphesHepMC2 exists, but its ROOT runtime "
                "linkage is not usable."
            ),
            required=False,
            details={
                "executable": str(executable),
                "runtime_problem": runtime_problem,
            },
            remediation=(
                "Rerun the installer with --with-delphes --yes "
                "to clean-rebuild Delphes against the active ROOT."
            ),
        )

    return _check(
        "delphes_installation",
        "Delphes installation",
        CheckStatus.PASS,
        "A runnable Delphes installation was found.",
        required=False,
        details={"executable": str(executable)},
    )


def _check_integrated_tools(
    mg5_executable: Path | None,
    paths_payload: dict[str, Any],
) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    root = _mg5_root(mg5_executable)

    pythia_configured = (
        _normalise_path(
            paths_payload.get("pythia8_path")
        )
        or _normalise_path(
            paths_payload.get("pythia8_executable")
        )
    )

    delphes_configured = (
        _normalise_path(
            paths_payload.get("delphes_path")
        )
        or _normalise_path(
            paths_payload.get("delphes_executable")
        )
    )

    pythia_candidates: list[Path] = []
    delphes_candidates: list[Path] = []

    if pythia_configured is not None:
        pythia_candidates.append(
            pythia_configured
        )

    if delphes_configured is not None:
        delphes_candidates.append(
            delphes_configured
        )

    if root is not None:
        pythia_candidates.append(
            root / "HEPTools" / "pythia8"
        )

        delphes_candidates.extend(
            [
                root / "Delphes",
                root / "HEPTools" / "Delphes",
                root / "HEPTools" / "delphes",
            ]
        )

    pythia, searched_pythia = (
        _find_first_executable(
            pythia_candidates,
            ("pythia8-config",),
        )
    )

    delphes, searched_delphes = (
        _find_first_executable(
            delphes_candidates,
            (
                "DelphesHepMC2",
                "DelphesHepMC",
                "DelphesHepMC3",
                "DelphesSTDHEP",
                "DelphesPythia8",
            ),
        )
    )

    checks.append(
        _pythia_installation_check(
            pythia,
            searched_pythia,
        )
    )

    checks.append(
        _delphes_installation_check(
            delphes,
            searched_delphes,
        )
    )

    return checks


def _mg5_deep_smoke(
    executable: Path,
    *,
    timeout_seconds: int,
) -> tuple[bool, str, dict[str, Any]]:
    with tempfile.TemporaryDirectory(
        prefix="hep_agent_doctor_mg5_"
    ) as temporary:
        root = Path(temporary)
        output = root / "SMOKE_PROCESS"

        script = "\n".join(
            [
                "import model sm",
                "generate e+ e- > mu+ mu-",
                f"output {output} -f",
                "quit",
                "",
            ]
        )

        try:
            completed = subprocess.run(
                [str(executable)],
                input=script,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return (
                False,
                "MG5 smoke test timed out.",
                {
                    "timeout_seconds": (
                        timeout_seconds
                    )
                },
            )
        except OSError as exc:
            return (
                False,
                "MG5 could not be launched.",
                {"error": str(exc)},
            )

        generated = (
            output / "Cards"
        ).is_dir()

        success = (
            completed.returncode == 0
            and generated
        )

        details = {
            "returncode": completed.returncode,
            "generated_output": generated,
            "stdout_tail": (
                completed.stdout[-3000:]
            ),
            "stderr_tail": (
                completed.stderr[-3000:]
            ),
        }

        if success:
            return (
                True,
                (
                    "MG5 generated a temporary "
                    "Standard Model process successfully."
                ),
                details,
            )

        return (
            False,
            (
                "MG5 launched but did not produce the "
                "expected temporary process directory."
            ),
            details,
        )


def run_doctor(
    *,
    project_root: Path | None = None,
    selected_profile: str = DEFAULT_PROFILE,
    ollama_host: str | None = None,
    deep: bool = False,
    timeout_seconds: int = 180,
) -> DoctorReport:
    """Run all configured environment checks."""

    root = (
        project_root
        or default_project_root()
    ).resolve()

    host = (
        ollama_host
        or os.environ.get(
            "OLLAMA_HOST"
        )
        or "http://localhost:11434"
    ).rstrip("/")

    checks: list[DoctorCheck] = []

    # -----------------------------------------------------
    # Python and dependencies
    # -----------------------------------------------------

    python_ok = (
        sys.version_info >= (3, 10)
    )

    checks.append(
        _check(
            "python_version",
            "Python version",
            (
                CheckStatus.PASS
                if python_ok
                else CheckStatus.FAILURE
            ),
            (
                "Supported Python version is active."
                if python_ok
                else "Python 3.10 or newer is required."
            ),
            details={
                "version": sys.version,
                "executable": sys.executable,
            },
            remediation=(
                None
                if python_ok
                else (
                    "Activate the project environment using "
                    "Python 3.10 or newer."
                )
            ),
        )
    )

    dependencies = {
        "pydantic": True,
        "streamlit": False,
    }

    for dependency, required in dependencies.items():
        available = (
            importlib.util.find_spec(
                dependency
            )
            is not None
        )

        checks.append(
            _check(
                f"dependency_{dependency}",
                f"Python dependency: {dependency}",
                (
                    CheckStatus.PASS
                    if available
                    else (
                        CheckStatus.FAILURE
                        if required
                        else CheckStatus.WARNING
                    )
                ),
                (
                    "Dependency is importable."
                    if available
                    else "Dependency is not importable."
                ),
                required=required,
                remediation=(
                    None
                    if available
                    else (
                        'Install the project with: '
                        'python -m pip install -e ".[web]"'
                    )
                ),
            )
        )

    # -----------------------------------------------------
    # Repository and writable directories
    # -----------------------------------------------------

    checks.append(
        _check(
            "project_root",
            "Project root",
            (
                CheckStatus.PASS
                if (
                    root.is_dir()
                    and (
                        root / "src"
                        / "hep_agent"
                    ).is_dir()
                )
                else CheckStatus.FAILURE
            ),
            (
                "HEP-agent repository was found."
                if (
                    root.is_dir()
                    and (
                        root / "src"
                        / "hep_agent"
                    ).is_dir()
                )
                else (
                    "The selected directory does not look "
                    "like the local HEP-agent repository."
                )
            ),
            details={"path": str(root)},
        )
    )

    checks.append(
        _check_writable_directory(
            root / "results",
            check_id="results_directory",
            label="Results directory",
        )
    )

    checks.append(
        _check_writable_directory(
            root / "results" / "runs",
            check_id="run_records_directory",
            label="Run-record directory",
        )
    )

    # -----------------------------------------------------
    # Configuration
    # -----------------------------------------------------

    profiles_path = (
        root
        / "configs"
        / "agent_profiles.json"
    )

    profiles_payload, profiles_error = (
        _load_json(profiles_path)
    )

    checks.append(
        _check(
            "agent_profiles_config",
            "Agent profiles configuration",
            (
                CheckStatus.PASS
                if profiles_error is None
                else CheckStatus.FAILURE
            ),
            (
                "Agent profiles JSON is valid."
                if profiles_error is None
                else profiles_error
            ),
            details={
                "path": str(profiles_path)
            },
            remediation=(
                None
                if profiles_error is None
                else (
                    "Restore a valid "
                    "configs/agent_profiles.json file."
                )
            ),
        )
    )

    selected_profile_payload: (
        dict[str, Any] | None
    ) = None

    if profiles_payload is not None:
        candidate = profiles_payload.get(
            selected_profile
        )

        if isinstance(candidate, dict):
            selected_profile_payload = candidate

    checks.append(
        _check(
            "selected_profile",
            "Selected model profile",
            (
                CheckStatus.PASS
                if selected_profile_payload
                is not None
                else CheckStatus.FAILURE
            ),
            (
                f"Profile {selected_profile!r} is available."
                if selected_profile_payload
                is not None
                else (
                    f"Profile {selected_profile!r} "
                    "does not exist."
                )
            ),
            details={
                "profile": selected_profile,
                "available_profiles": (
                    sorted(
                        profiles_payload.keys()
                    )
                    if profiles_payload
                    is not None
                    else []
                ),
            },
            remediation=(
                None
                if selected_profile_payload
                is not None
                else (
                    "Choose an existing profile or add it "
                    "to configs/agent_profiles.json."
                )
            ),
        )
    )

    paths_config = _discover_paths_config(
        root
    )

    paths_payload: dict[str, Any] = {}

    if paths_config is None:
        checks.append(
            _check(
                "tool_paths_config",
                "HEP-tool paths configuration",
                CheckStatus.FAILURE,
                (
                    "No local tool-path JSON file "
                    "could be identified."
                ),
                remediation=(
                    "Create configs/local_paths.json "
                    "with at least mg5_executable."
                ),
            )
        )

    else:
        loaded_paths, paths_error = (
            _load_json(paths_config)
        )

        if loaded_paths is not None:
            paths_payload = loaded_paths

        checks.append(
            _check(
                "tool_paths_config",
                "HEP-tool paths configuration",
                (
                    CheckStatus.PASS
                    if paths_error is None
                    else CheckStatus.FAILURE
                ),
                (
                    "HEP-tool paths JSON is valid."
                    if paths_error is None
                    else paths_error
                ),
                details={
                    "path": str(paths_config)
                },
                remediation=(
                    None
                    if paths_error is None
                    else (
                        "Correct the invalid paths "
                        "configuration JSON."
                    )
                ),
            )
        )

    # -----------------------------------------------------
    # Ollama and models
    # -----------------------------------------------------

    model_names, ollama_error = (
        _get_ollama_tags(host)
    )

    checks.append(
        _check(
            "ollama_connection",
            "Ollama connection",
            (
                CheckStatus.PASS
                if ollama_error is None
                else CheckStatus.FAILURE
            ),
            (
                "Ollama API is reachable."
                if ollama_error is None
                else ollama_error
            ),
            details={
                "host": host,
                "models_found": (
                    len(model_names)
                    if model_names is not None
                    else 0
                ),
            },
            remediation=(
                None
                if ollama_error is None
                else (
                    "Start Ollama and verify OLLAMA_HOST."
                )
            ),
        )
    )

    primary_model = None
    fallback_model = None

    if selected_profile_payload:
        primary = selected_profile_payload.get(
            "primary_model"
        )
        fallback = selected_profile_payload.get(
            "fallback_model"
        )

        if isinstance(primary, str):
            primary_model = primary

        if isinstance(fallback, str):
            fallback_model = fallback

    if model_names is not None:
        for role, model, required in (
            (
                "primary",
                primary_model,
                True,
            ),
            (
                "fallback",
                fallback_model,
                False,
            ),
        ):
            if model is None:
                if role == "fallback":
                    checks.append(
                        _check(
                            "fallback_model",
                            "Fallback model",
                            CheckStatus.PASS,
                            (
                                "The selected profile does "
                                "not require a fallback model."
                            ),
                            required=False,
                        )
                    )
                continue

            available = model in model_names

            checks.append(
                _check(
                    f"{role}_model",
                    (
                        "Primary model"
                        if role == "primary"
                        else "Fallback model"
                    ),
                    (
                        CheckStatus.PASS
                        if available
                        else (
                            CheckStatus.FAILURE
                            if required
                            else CheckStatus.WARNING
                        )
                    ),
                    (
                        f"Model {model!r} is available."
                        if available
                        else (
                            f"Model {model!r} is not listed "
                            "by the configured Ollama host."
                        )
                    ),
                    required=required,
                    details={
                        "model": model,
                    },
                    remediation=(
                        None
                        if available
                        else (
                            f"Pull or make the model available: "
                            f"ollama pull {model}"
                        )
                    ),
                )
            )

    if (
        deep
        and ollama_error is None
        and primary_model is not None
    ):
        content, chat_error = (
            _ollama_chat_smoke(
                host,
                primary_model,
                timeout_seconds=(
                    timeout_seconds
                ),
            )
        )

        checks.append(
            _check(
                "ollama_chat_smoke",
                "Primary-model live response",
                (
                    CheckStatus.PASS
                    if chat_error is None
                    else CheckStatus.FAILURE
                ),
                (
                    "The primary model returned a live response."
                    if chat_error is None
                    else chat_error
                ),
                details={
                    "model": primary_model,
                    "response": content,
                },
                remediation=(
                    None
                    if chat_error is None
                    else (
                        "Check model availability, Ollama logs, "
                        "network access, and the configured timeout."
                    )
                ),
            )
        )

    # -----------------------------------------------------
    # HEP tools
    # -----------------------------------------------------

    mg5_executable = _normalise_path(
        paths_payload.get(
            "mg5_executable"
        )
    )

    ma5_executable = (
        _normalise_path(
            paths_payload.get(
                "madanalysis5_executable"
            )
        )
        or _normalise_path(
            paths_payload.get(
                "ma5_executable"
            )
        )
    )

    checks.append(
        _check_executable(
            check_id="mg5_executable",
            label="MadGraph5_aMC executable",
            path=mg5_executable,
            required=True,
            remediation=(
                "Configure the correct mg5_executable "
                "in the local paths JSON file."
            ),
        )
    )

    checks.append(
        _check_executable(
            check_id="madanalysis5_executable",
            label="MadAnalysis5 executable",
            path=ma5_executable,
            required=False,
            remediation=(
                "Configure madanalysis5_executable if "
                "MadAnalysis support is required."
            ),
        )
    )

    checks.extend(
        _check_integrated_tools(
            mg5_executable,
            paths_payload,
        )
    )

    if (
        deep
        and mg5_executable is not None
        and mg5_executable.is_file()
        and os.access(
            mg5_executable,
            os.X_OK,
        )
    ):
        (
            success,
            summary,
            details,
        ) = _mg5_deep_smoke(
            mg5_executable,
            timeout_seconds=(
                timeout_seconds
            ),
        )

        checks.append(
            _check(
                "mg5_generation_smoke",
                "MG5 process-generation smoke test",
                (
                    CheckStatus.PASS
                    if success
                    else CheckStatus.FAILURE
                ),
                summary,
                details=details,
                remediation=(
                    None
                    if success
                    else (
                        "Inspect the captured MG5 output, "
                        "Python compatibility, and MG5 installation."
                    )
                ),
            )
        )

    # -----------------------------------------------------
    # Documentation and repository utilities
    # -----------------------------------------------------

    guide = (
        root
        / "docs"
        / "REPOSITORY_GUIDE.md"
    )

    manifest = (
        root
        / "docs"
        / "REPOSITORY_MANIFEST.json"
    )

    documentation_ok = (
        guide.is_file()
        and manifest.is_file()
    )

    checks.append(
        _check(
            "repository_documentation",
            "Repository guide and manifest",
            (
                CheckStatus.PASS
                if documentation_ok
                else CheckStatus.WARNING
            ),
            (
                "Repository guide and manifest are present."
                if documentation_ok
                else (
                    "Repository guide or manifest is missing."
                )
            ),
            required=False,
            details={
                "guide": str(guide),
                "manifest": str(manifest),
            },
            remediation=(
                None
                if documentation_ok
                else (
                    "Run scripts/generate_repository_guide.py."
                )
            ),
        )
    )

    git_available = (
        shutil.which("git")
        is not None
    )

    checks.append(
        _check(
            "git_command",
            "Git command",
            (
                CheckStatus.PASS
                if git_available
                else CheckStatus.WARNING
            ),
            (
                "Git is available."
                if git_available
                else "Git is not available on PATH."
            ),
            required=False,
        )
    )

    return DoctorReport.create(
        project_root=root,
        selected_profile=selected_profile,
        deep_checks=deep,
        checks=checks,
    )
