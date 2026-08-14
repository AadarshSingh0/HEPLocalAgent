"""Live native-linkage audit derived only from a validated stack manifest."""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Mapping

from .linkage import inspect_native_linkage
from .stack import StackManifest, build_stack_environment


def _managed_library(directory: Path, stem: str) -> Path:
    for suffix in (".dylib", ".so", ".a"):
        candidate = directory / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    return directory / f"{stem}.missing"


def managed_linkage_targets(manifest: StackManifest) -> dict[str, Path]:
    """Return the authoritative native target set for Linux and Darwin."""

    stack = manifest.stack_root
    ma5_lib = stack / "madanalysis5/tools/SampleAnalyzer/Lib"
    return {
        "root": manifest.root_prefix / "bin/root.exe",
        "pythia8": _managed_library(
            Path(manifest.components["pythia8"]["prefix"]) / "lib", "libpythia8"
        ),
        "hepmc2": _managed_library(stack / "hepmc2/lib", "libHepMC"),
        "delphes": stack / "delphes/DelphesHepMC2",
        "libDelphes": _managed_library(stack / "delphes", "libDelphes"),
        "mg5amc_py8_interface": stack / "mg5amc_py8_interface/MG5aMC_PY8_interface",
        "ma5_root": _managed_library(ma5_lib, "libroot_for_ma5"),
        "ma5_delphes": _managed_library(ma5_lib, "libdelphes_for_ma5"),
        "ma5_test_root": stack / "madanalysis5/tools/SampleAnalyzer/Bin/TestRoot",
        "ma5_test_delphes": stack / "madanalysis5/tools/SampleAnalyzer/Bin/TestDelphes",
    }


def audit_managed_linkage(
    manifest: StackManifest,
    *,
    environment: Mapping[str, str] | None = None,
) -> tuple[dict[str, dict[str, object]], list[str]]:
    """Re-run linkage checks and compare the target set with the manifest."""

    stack = manifest.stack_root.resolve()
    process_environment = (
        dict(environment)
        if environment is not None
        else build_stack_environment(manifest)
    )
    recorded = manifest.payload.get("linkage_validation", {})
    python_payload = manifest.payload.get("python", {})
    legacy_verified_linux = (
        platform.system() == "Linux"
        and isinstance(python_payload, dict)
        and "runtime_provider" not in python_payload
        and isinstance(recorded, dict)
    )
    if legacy_verified_linux:
        targets = {
            name: Path(str(result.get("target", "")))
            for name, result in recorded.items()
            if isinstance(result, dict)
        }
    else:
        targets = managed_linkage_targets(manifest)
    reports: dict[str, dict[str, object]] = {}
    failures: list[str] = []
    for name, raw_target in targets.items():
        target = raw_target.resolve(strict=False)
        if not target.is_relative_to(stack):
            failures.append(f"{name}: target escapes managed stack: {target}")
            continue
        if not target.is_file():
            failures.append(f"{name}: missing native target: {target}")
            continue
        report = inspect_native_linkage(
            target,
            stack,
            environment=process_environment,
            enforce_system_libcpp=platform.system() == "Darwin" and name == "pythia8",
        )
        reports[name] = report
        if report.get("passed") is not True:
            raw_failures = report.get("failures")
            details = raw_failures if isinstance(raw_failures, list) else ["linkage failed"]
            failures.extend(f"{name}: {failure}" for failure in details)

    if not isinstance(recorded, dict) or set(recorded) != set(targets):
        failures.append(
            "manifest linkage target set disagrees with the authoritative audit target set"
        )
    else:
        for name, report in reports.items():
            result = recorded.get(name)
            if not isinstance(result, dict) or result.get("target") != report.get("target"):
                failures.append(f"{name}: current linkage target disagrees with manifest")
    return reports, failures
