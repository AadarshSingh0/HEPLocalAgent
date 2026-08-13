"""One clone-owned contract for every HEP subprocess.

The stack manifest is the only publication-default source of HEP paths.  This
module deliberately does not discover ROOT or other HEP programs from PATH.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


STACK_MANIFEST_SCHEMA = "hep-local-agent-stack-v1"
MANIFEST_RELATIVE_PATH = Path(".hep-stack/manifest.json")

_CONFLICTING_VARIABLES = {
    "CMAKE_PREFIX_PATH",
    "CPATH",
    "C_INCLUDE_PATH",
    "CPLUS_INCLUDE_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
    "LD_LIBRARY_PATH",
    "LIBRARY_PATH",
    "PKG_CONFIG_PATH",
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHIA8DATA",
    "ROOT_INCLUDE_PATH",
    "ROOTSYS",
    "VIRTUAL_ENV",
}

_MINIMAL_OS_PATH = (
    "/usr/sbin",
    "/usr/bin",
    "/sbin",
    "/bin",
)


class StackConfigurationError(ValueError):
    """The managed stack manifest is missing, stale, or unsafe."""


def _absolute_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise StackConfigurationError(f"Stack manifest is missing {label!r}.")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise StackConfigurationError(
            f"Stack manifest path {label!r} must be absolute: {value!r}."
        )
    return path.absolute()


def _inside(path: Path, boundary: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(boundary.resolve(strict=False))
    except ValueError:
        return False
    return True


def _lexically_inside(path: Path, boundary: Path) -> bool:
    """Check ownership of a path entry while permitting venv interpreter symlinks."""
    try:
        path.absolute().relative_to(boundary.absolute())
    except ValueError:
        return False
    return True


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise StackConfigurationError(f"Stack manifest {label!r} must be an object.")
    return value


@dataclass(frozen=True)
class StackManifest:
    """Validated paths for one repository-owned HEP installation."""

    path: Path
    installation_id: str
    repository_root: Path
    stack_root: Path
    python_prefix: Path
    python_executable: Path
    root_prefix: Path
    root_config: Path
    pythia8_data: Path
    library_paths: tuple[Path, ...]
    executables: Mapping[str, Path]
    components: Mapping[str, Mapping[str, object]]
    payload: Mapping[str, object]

    def executable(self, component: str) -> Path:
        try:
            return self.executables[component]
        except KeyError as exc:
            raise StackConfigurationError(
                f"Stack manifest has no executable for {component!r}."
            ) from exc


def default_manifest_path(repository_root: str | Path | None = None) -> Path:
    """Return the clone-local manifest path without probing elsewhere."""

    if repository_root is None:
        repository_root = Path(__file__).resolve().parents[3]
    return Path(repository_root).expanduser().absolute() / MANIFEST_RELATIVE_PATH


def load_stack_manifest(
    manifest_path: str | Path | None = None,
    *,
    expected_repository_root: str | Path | None = None,
    require_files: bool = True,
) -> StackManifest:
    """Load and validate a clone-owned stack manifest.

    No fallback discovery is attempted.  Every HEP prefix and executable must
    remain within the manifest's clone-local ``.hep-stack`` boundary.
    """

    expected_root = Path(
        expected_repository_root
        if expected_repository_root is not None
        else Path(__file__).resolve().parents[3]
    ).expanduser().absolute()
    path = Path(
        manifest_path if manifest_path is not None else default_manifest_path(expected_root)
    ).expanduser().absolute()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StackConfigurationError(
            f"Could not read managed stack manifest {path}: {exc}. "
            "Run the installer in this repository clone."
        ) from exc
    if not isinstance(payload, dict):
        raise StackConfigurationError("Stack manifest must be a JSON object.")
    if payload.get("schema_version") != STACK_MANIFEST_SCHEMA:
        raise StackConfigurationError(
            f"Unsupported stack schema {payload.get('schema_version')!r}; "
            f"expected {STACK_MANIFEST_SCHEMA!r}."
        )
    installation_id = payload.get("installation_id")
    if not isinstance(installation_id, str) or not installation_id.strip():
        raise StackConfigurationError("Stack manifest has no installation ID.")

    repository_root = _absolute_path(payload.get("repository_root"), "repository_root")
    stack_root = _absolute_path(payload.get("stack_root"), "stack_root")
    if repository_root != expected_root:
        raise StackConfigurationError(
            "Stack manifest belongs to a different repository clone: "
            f"{repository_root}. Current clone is {expected_root}."
        )
    expected_stack = repository_root / ".hep-stack"
    if stack_root != expected_stack:
        raise StackConfigurationError(
            f"Managed stack must be clone-local at {expected_stack}, not {stack_root}."
        )
    if path != stack_root / "manifest.json":
        raise StackConfigurationError(
            f"Manifest must live inside its stack at {stack_root / 'manifest.json'}."
        )

    recorded_platform = _mapping(payload.get("platform"), "platform")
    if recorded_platform.get("system") != platform.system():
        raise StackConfigurationError("Stack manifest was created for another operating system.")
    if recorded_platform.get("machine") != platform.machine():
        raise StackConfigurationError("Stack manifest was created for another architecture.")

    python = _mapping(payload.get("python"), "python")
    python_prefix = _absolute_path(python.get("prefix"), "python.prefix")
    python_executable = _absolute_path(python.get("executable"), "python.executable")
    expected_python_prefix = repository_root / ".venv"
    if python_prefix != expected_python_prefix or not _lexically_inside(
        python_executable, expected_python_prefix
    ):
        raise StackConfigurationError(
            "Managed Python must belong to this clone's .venv. "
            f"Recorded executable: {python_executable}."
        )
    current_python = Path(sys.executable).absolute()
    if current_python != python_executable:
        raise StackConfigurationError(
            "This process is not running with the Python recorded by the stack: "
            f"{current_python}; expected {python_executable}."
        )

    runtime = _mapping(payload.get("runtime"), "runtime")
    root_prefix = _absolute_path(runtime.get("root_prefix"), "runtime.root_prefix")
    root_config = _absolute_path(runtime.get("root_config"), "runtime.root_config")
    pythia8_data = _absolute_path(runtime.get("pythia8_data"), "runtime.pythia8_data")
    raw_libraries = runtime.get("library_paths")
    if not isinstance(raw_libraries, list) or not raw_libraries:
        raise StackConfigurationError("Stack manifest runtime.library_paths must be a list.")
    library_paths = tuple(
        _absolute_path(value, f"runtime.library_paths[{index}]")
        for index, value in enumerate(raw_libraries)
    )

    components_raw = _mapping(payload.get("components"), "components")
    required_components = ("madgraph", "pythia8", "root", "delphes", "madanalysis5")
    components: dict[str, Mapping[str, object]] = {}
    executables: dict[str, Path] = {}
    for name in required_components:
        component = _mapping(components_raw.get(name), f"components.{name}")
        for field in ("version", "source", "prefix", "executables", "smoke_test"):
            if field not in component:
                raise StackConfigurationError(f"Component {name!r} is missing {field!r}.")
        prefix = _absolute_path(component.get("prefix"), f"components.{name}.prefix")
        if not _inside(prefix, stack_root):
            raise StackConfigurationError(f"Component {name!r} escapes managed stack: {prefix}.")
        component_executables = _mapping(
            component.get("executables"), f"components.{name}.executables"
        )
        for executable_name in ("primary", "native"):
            managed_executable = _absolute_path(
                component_executables.get(executable_name),
                f"components.{name}.executables.{executable_name}",
            )
            if not _inside(managed_executable, stack_root):
                raise StackConfigurationError(
                    f"Executable {executable_name!r} for {name!r} escapes "
                    f"managed stack: {managed_executable}."
                )
            if require_files and (
                not managed_executable.is_file()
                or not os.access(managed_executable, os.X_OK)
            ):
                raise StackConfigurationError(
                    f"Executable {executable_name!r} for {name!r} is not "
                    f"runnable: {managed_executable}."
                )
        primary = _absolute_path(component_executables["primary"], "primary")
        source = _mapping(component.get("source"), f"components.{name}.source")
        checksum = source.get("sha256")
        if (
            not isinstance(source.get("url"), str)
            or not isinstance(checksum, str)
            or len(checksum) != 64
        ):
            raise StackConfigurationError(
                f"Component {name!r} must record a source URL and SHA-256 checksum."
            )
        smoke = _mapping(component.get("smoke_test"), f"components.{name}.smoke_test")
        if smoke.get("passed") is not True:
            raise StackConfigurationError(f"Component {name!r} has not passed its smoke test.")
        components[name] = component
        executables[name] = primary

    root_component_prefix = _absolute_path(
        components["root"].get("prefix"), "components.root.prefix"
    )
    pythia_component_prefix = _absolute_path(
        components["pythia8"].get("prefix"), "components.pythia8.prefix"
    )
    root_component_executable = _absolute_path(
        _mapping(
            components["root"].get("executables"), "root executables"
        ).get("native"),
        "components.root.executables.native",
    )
    if root_prefix != root_component_prefix or root_config != root_component_executable:
        raise StackConfigurationError(
            "Runtime ROOT prefix/root-config disagree with the ROOT component."
        )
    if not _inside(pythia8_data, pythia_component_prefix):
        raise StackConfigurationError(
            "Runtime Pythia XML data does not belong to the Pythia component."
        )

    for label, managed_path in (
        ("ROOT prefix", root_prefix),
        ("root-config", root_config),
        ("Pythia XML data", pythia8_data),
        *(("runtime library path", item) for item in library_paths),
    ):
        if not _inside(managed_path, stack_root):
            raise StackConfigurationError(f"{label} escapes managed stack: {managed_path}.")

    linkage = _mapping(payload.get("linkage_validation"), "linkage_validation")
    if not linkage:
        raise StackConfigurationError("Stack manifest has no native linkage validation.")
    for name, raw_result in linkage.items():
        result = _mapping(raw_result, f"linkage_validation.{name}")
        if result.get("passed") is not True:
            raise StackConfigurationError(
                f"Native linkage validation failed for {name!r}."
            )
        target = _absolute_path(
            result.get("target"), f"linkage_validation.{name}.target"
        )
        if not _inside(target, stack_root):
            raise StackConfigurationError(
                f"Linkage target escapes managed stack: {target}."
            )
        output = result.get("output", [])
        if not isinstance(output, list) or not all(
            isinstance(line, str) for line in output
        ):
            raise StackConfigurationError(
                f"Linkage output for {name!r} must be a list of strings."
            )
        for line in output:
            lowered = line.lower()
            hep_library = any(
                token in lowered
                for token in ("libcore", "libtree", "libpythia", "libhepmc", "libdelphes")
            )
            absolute_tokens = [
                token for token in line.replace("=>", " ").split() if token.startswith("/")
            ]
            external_hep_path = any(
                not _inside(Path(token), stack_root)
                for token in absolute_tokens
            )
            if hep_library and external_hep_path:
                raise StackConfigurationError(
                    f"Native HEP library for {name!r} resolves outside managed stack: {line.strip()}"
                )

    ownership = _mapping(payload.get("ownership"), "ownership")
    if ownership.get("installation_id") != installation_id:
        raise StackConfigurationError("Stack ownership does not match installation ID.")
    if ownership.get("boundary") != str(stack_root):
        raise StackConfigurationError("Stack ownership boundary does not match stack_root.")

    if require_files:
        for label, managed_path in (
            ("Python executable", python_executable),
            ("root-config", root_config),
            *((f"{name} executable", executable) for name, executable in executables.items()),
        ):
            if not managed_path.is_file() or not os.access(managed_path, os.X_OK):
                raise StackConfigurationError(f"{label} is not runnable: {managed_path}.")
        for label, managed_path in (
            ("stack root", stack_root),
            ("ROOT prefix", root_prefix),
            ("Pythia XML data", pythia8_data),
            *(("runtime library path", item) for item in library_paths),
        ):
            if not managed_path.is_dir():
                raise StackConfigurationError(f"{label} does not exist: {managed_path}.")

    return StackManifest(
        path=path,
        installation_id=installation_id,
        repository_root=repository_root,
        stack_root=stack_root,
        python_prefix=python_prefix,
        python_executable=python_executable,
        root_prefix=root_prefix,
        root_config=root_config,
        pythia8_data=pythia8_data,
        library_paths=library_paths,
        executables=executables,
        components=components,
        payload=payload,
    )


def load_configured_stack(
    paths_config: str | Path,
    *,
    expected_repository_root: str | Path | None = None,
) -> StackManifest:
    """Load local_paths.json and require exact agreement with its manifest."""

    config_path = Path(paths_config).expanduser().absolute()
    repository_root = Path(
        expected_repository_root
        if expected_repository_root is not None
        else config_path.parent.parent
    ).expanduser().absolute()
    try:
        configuration = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StackConfigurationError(
            f"Could not read managed path configuration {config_path}: {exc}."
        ) from exc
    if not isinstance(configuration, dict):
        raise StackConfigurationError("Managed path configuration must be an object.")
    configured_manifest = configuration.get("stack_manifest")
    expected_manifest = repository_root / MANIFEST_RELATIVE_PATH
    if (
        not isinstance(configured_manifest, str)
        or Path(configured_manifest).absolute() != expected_manifest
    ):
        raise StackConfigurationError(
            f"local_paths.json must select this clone's manifest: {expected_manifest}."
        )
    manifest = load_stack_manifest(
        expected_manifest,
        expected_repository_root=repository_root,
    )
    agreements = {
        "mg5_executable": manifest.executable("madgraph"),
        "madanalysis5_executable": manifest.executable("madanalysis5"),
        "pythia8_path": Path(str(manifest.components["pythia8"]["prefix"])),
        "delphes_path": Path(str(manifest.components["delphes"]["prefix"])),
        "root_prefix": manifest.root_prefix,
    }
    for key, expected in agreements.items():
        value = configuration.get(key)
        if not isinstance(value, str) or Path(value).absolute() != expected.absolute():
            raise StackConfigurationError(
                f"Configured {key!r} disagrees with managed stack manifest: "
                f"{value!r}; expected {str(expected)!r}."
            )
    return manifest


def _remove_conflicting_variables(environment: dict[str, str]) -> None:
    for variable in tuple(environment):
        if (
            variable in _CONFLICTING_VARIABLES
            or variable.startswith("CONDA_")
            or variable.startswith("_CE_")
        ):
            environment.pop(variable, None)


def build_controlled_environment(
    *,
    repository_root: str | Path,
    stack_root: str | Path,
    python_prefix: str | Path,
    root_prefix: str | Path,
    pythia8_data: str | Path,
    library_paths: tuple[str | Path, ...],
    executable_directories: tuple[str | Path, ...] = (),
    inherited: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the shared environment from an explicitly owned stack layout.

    The installer uses this form before the final manifest exists. Runtime
    callers use :func:`build_stack_environment`, which supplies the exact same
    inputs from the validated manifest.
    """

    repository = Path(repository_root).expanduser().absolute()
    stack = Path(stack_root).expanduser().absolute()
    python = Path(python_prefix).expanduser().absolute()
    root = Path(root_prefix).expanduser().absolute()
    pythia_data = Path(pythia8_data).expanduser().absolute()
    libraries = tuple(Path(item).expanduser().absolute() for item in library_paths)
    executable_bins = tuple(
        Path(item).expanduser().absolute() for item in executable_directories
    )
    if stack != repository / ".hep-stack":
        raise StackConfigurationError(
            f"Managed stack must be clone-local at {repository / '.hep-stack'}."
        )
    if python != repository / ".venv":
        raise StackConfigurationError(
            f"Managed Python must be clone-local at {repository / '.venv'}."
        )
    for label, path in (
        ("ROOT prefix", root),
        ("Pythia XML data", pythia_data),
        *(("runtime library path", item) for item in libraries),
        *(("executable directory", item) for item in executable_bins),
    ):
        if not _inside(path, stack):
            raise StackConfigurationError(f"{label} escapes managed stack: {path}.")

    environment = dict(os.environ if inherited is None else inherited)
    _remove_conflicting_variables(environment)
    path_entries = (
        stack / "launchers",
        python / "bin",
        root / "bin",
        *executable_bins,
        *(Path(item) for item in _MINIMAL_OS_PATH),
    )
    environment["PATH"] = os.pathsep.join(
        dict.fromkeys(str(item) for item in path_entries)
    )
    environment["VIRTUAL_ENV"] = str(python)
    environment["ROOTSYS"] = str(root)
    environment["PYTHIA8DATA"] = str(pythia_data)
    environment["PYTHONNOUSERSITE"] = "1"
    library_value = os.pathsep.join(str(item) for item in libraries)
    if platform.system() == "Darwin":
        environment["DYLD_LIBRARY_PATH"] = library_value
    else:
        environment["LD_LIBRARY_PATH"] = library_value
    pythia_prefix = pythia_data.parents[2]
    environment["CMAKE_PREFIX_PATH"] = os.pathsep.join(
        (str(root), str(pythia_prefix))
    )
    environment["PKG_CONFIG_PATH"] = os.pathsep.join(
        str(item / "pkgconfig") for item in libraries
    )
    return environment


def build_stack_environment(
    manifest: StackManifest | str | Path,
    *,
    inherited: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the exact environment shared by all managed HEP subprocesses."""

    if not isinstance(manifest, StackManifest):
        manifest = load_stack_manifest(manifest)
    component_bins = []
    for name in ("root", "madgraph", "pythia8", "delphes", "madanalysis5"):
        parent = manifest.executable(name).parent
        if parent not in component_bins:
            component_bins.append(parent)
    return build_controlled_environment(
        repository_root=manifest.repository_root,
        stack_root=manifest.stack_root,
        python_prefix=manifest.python_prefix,
        root_prefix=manifest.root_prefix,
        pythia8_data=manifest.pythia8_data,
        library_paths=manifest.library_paths,
        executable_directories=tuple(component_bins),
        inherited=inherited,
    )
