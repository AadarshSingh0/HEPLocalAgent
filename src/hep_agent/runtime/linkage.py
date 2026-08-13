"""Platform-neutral native linkage inspection for the managed HEP stack."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Mapping


def _inside(path: Path, boundary: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(boundary.resolve(strict=False))
    except ValueError:
        return False
    return True


def _allowed_system_library(path: Path, system: str) -> bool:
    prefixes = (
        (Path("/System/Library"), Path("/usr/lib"))
        if system == "Darwin"
        else (Path("/lib"), Path("/lib64"), Path("/usr/lib"), Path("/usr/lib64"))
    )
    return any(path == prefix or path.is_relative_to(prefix) for prefix in prefixes)


def _macho_rpaths(output: str, target: Path) -> list[Path]:
    lines = output.splitlines()
    raw_paths: list[str] = []
    for index, line in enumerate(lines):
        if line.strip() != "cmd LC_RPATH":
            continue
        for candidate in lines[index + 1 : index + 5]:
            stripped = candidate.strip()
            if stripped.startswith("path "):
                raw_paths.append(stripped[5:].split(" (offset", 1)[0])
                break

    resolved: list[Path] = []
    for raw in raw_paths:
        if raw.startswith("@loader_path") or raw.startswith("@executable_path"):
            suffix = raw.split("/", 1)[1] if "/" in raw else ""
            resolved.append((target.parent / suffix).resolve(strict=False))
        elif raw.startswith("/"):
            resolved.append(Path(raw).resolve(strict=False))
    return resolved


def _resolve_macho_dependency(
    dependency: str,
    *,
    target: Path,
    rpaths: list[Path],
) -> Path | None:
    if dependency.startswith("/"):
        return Path(dependency).resolve(strict=False)
    if dependency.startswith("@loader_path") or dependency.startswith("@executable_path"):
        suffix = dependency.split("/", 1)[1] if "/" in dependency else ""
        return (target.parent / suffix).resolve(strict=False)
    if dependency.startswith("@rpath/"):
        suffix = dependency[len("@rpath/") :]
        candidates = [(rpath / suffix).resolve(strict=False) for rpath in rpaths]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0] if len(candidates) == 1 else None
    if not dependency.startswith("@"):
        return (target.parent / dependency).resolve(strict=False)
    return None


def validate_macho_linkage(
    target: Path,
    stack_root: Path,
    libraries_output: str,
    load_commands_output: str,
    *,
    enforce_system_libcpp: bool = False,
) -> dict[str, object]:
    """Validate pre-captured ``otool`` output (also useful for hermetic tests)."""

    dependencies: list[str] = []
    for line in libraries_output.splitlines()[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        dependencies.append(stripped.split(" (compatibility", 1)[0])

    # For Mach-O shared libraries, the first entry emitted by ``otool -L`` is
    # LC_ID_DYLIB (the library's own install name), not a loaded dependency.
    if target.suffix in {".dylib", ".so"} and dependencies:
        dependencies = dependencies[1:]

    rpaths = _macho_rpaths(load_commands_output, target)
    failures: list[str] = []
    resolved_paths: list[str] = []
    for dependency in dependencies:
        resolved = _resolve_macho_dependency(
            dependency,
            target=target,
            rpaths=rpaths,
        )
        if resolved is None:
            failures.append(f"could not resolve managed dependency: {dependency}")
            continue
        if _allowed_system_library(resolved, "Darwin"):
            continue
        resolved_paths.append(str(resolved))
        if not _inside(resolved, stack_root):
            failures.append(f"library resolves outside stack: {dependency} -> {resolved}")

    if enforce_system_libcpp:
        libcxx = [item for item in dependencies if "libc++.1.dylib" in item]
        if libcxx != ["/usr/lib/libc++.1.dylib"]:
            failures.append(
                "Pythia must use the operating-system libc++ at "
                f"/usr/lib/libc++.1.dylib, observed: {libcxx or 'none'}"
            )

    return {
        "passed": not failures,
        "tool": "otool",
        "target": str(target),
        "output": libraries_output.splitlines(),
        "rpaths": [str(path) for path in rpaths],
        "resolved_paths": resolved_paths,
        "failures": failures,
    }


def inspect_native_linkage(
    target: str | Path,
    stack_root: str | Path,
    *,
    environment: Mapping[str, str] | None = None,
    system: str | None = None,
    enforce_system_libcpp: bool = False,
) -> dict[str, object]:
    """Inspect ELF or Mach-O linkage and reject external HEP dependencies."""

    target_path = Path(target).resolve(strict=False)
    stack_path = Path(stack_root).resolve(strict=False)
    operating_system = system or platform.system()
    if not _inside(target_path, stack_path):
        return {
            "passed": False,
            "tool": "otool" if operating_system == "Darwin" else "ldd",
            "target": str(target_path),
            "output": [],
            "resolved_paths": [],
            "failures": [f"linkage target escapes managed stack: {target_path}"],
        }

    process_environment = dict(os.environ if environment is None else environment)
    if target_path.suffix == ".a":
        archive = subprocess.run(
            ["/usr/bin/ar", "-t", str(target_path)],
            capture_output=True,
            text=True,
            check=False,
            env=process_environment,
            timeout=60,
        )
        output = archive.stdout + archive.stderr
        failures = [] if archive.returncode == 0 and archive.stdout.strip() else [
            "ar could not inspect the managed static archive"
        ]
        return {
            "passed": not failures, "tool": "ar", "target": str(target_path),
            "output": output.splitlines(), "resolved_paths": [], "failures": failures,
        }
    if operating_system == "Darwin":
        libraries = subprocess.run(
            ["/usr/bin/otool", "-L", str(target_path)],
            capture_output=True,
            text=True,
            check=False,
            env=process_environment,
            timeout=60,
        )
        load_commands = subprocess.run(
            ["/usr/bin/otool", "-l", str(target_path)],
            capture_output=True,
            text=True,
            check=False,
            env=process_environment,
            timeout=60,
        )
        if libraries.returncode != 0 or load_commands.returncode != 0:
            output = libraries.stdout + libraries.stderr + load_commands.stdout + load_commands.stderr
            return {
                "passed": False,
                "tool": "otool",
                "target": str(target_path),
                "output": output.splitlines(),
                "resolved_paths": [],
                "failures": ["otool could not inspect the Mach-O target"],
            }
        return validate_macho_linkage(
            target_path,
            stack_path,
            libraries.stdout,
            load_commands.stdout,
            enforce_system_libcpp=enforce_system_libcpp,
        )

    completed = subprocess.run(
        ["/usr/bin/ldd", str(target_path)],
        capture_output=True,
        text=True,
        check=False,
        env=process_environment,
        timeout=60,
    )
    output = completed.stdout + completed.stderr
    failures: list[str] = []
    resolved_paths: list[str] = []
    if completed.returncode != 0:
        failures.append("ldd could not inspect the ELF target")
    if "not found" in output:
        failures.append("ldd reported a missing library")
    for line in output.splitlines():
        absolute = [
            Path(token)
            for token in line.replace("=>", " ").split()
            if token.startswith("/")
        ]
        for resolved in absolute:
            canonical = resolved.resolve(strict=False)
            if _allowed_system_library(canonical, "Linux"):
                continue
            resolved_paths.append(str(canonical))
            if not _inside(canonical, stack_path):
                failures.append(f"library resolves outside stack: {line.strip()}")
    return {
        "passed": not failures,
        "tool": "ldd",
        "target": str(target_path),
        "output": output.splitlines(),
        "resolved_paths": resolved_paths,
        "failures": failures,
    }
