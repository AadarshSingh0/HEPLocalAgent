"""Doctor checks for the authoritative clone-owned HEP stack."""

from __future__ import annotations

import os
from pathlib import Path

from hep_agent.doctor.models import CheckStatus, DoctorCheck
from hep_agent.runtime import StackConfigurationError, load_configured_stack


def managed_stack_checks(project_root: Path) -> list[DoctorCheck]:
    """Report ownership, version, manifest, linkage, and smoke evidence."""

    manifest_path = project_root / ".hep-stack/manifest.json"
    try:
        manifest = load_configured_stack(
            project_root / "configs/local_paths.json",
            expected_repository_root=project_root,
        )
    except StackConfigurationError as exc:
        return [
            DoctorCheck(
                check_id="managed_stack_manifest",
                label="Managed HEP stack manifest",
                status=CheckStatus.FAILURE,
                summary=str(exc),
                remediation="Run ./install.sh to create a fresh clone-owned HEP stack.",
                details={"expected_manifest": str(manifest_path)},
            )
        ]

    checks = [
        DoctorCheck(
            check_id="managed_stack_manifest",
            label="Managed HEP stack manifest",
            status=CheckStatus.PASS,
            summary="Manifest schema, clone ownership, platform, and runtime paths agree.",
            details={
                "manifest": str(manifest.path),
                "installation_id": manifest.installation_id,
                "ownership_boundary": str(manifest.stack_root),
                "repository_root": str(manifest.repository_root),
                "root_prefix": str(manifest.root_prefix),
                "root_config": str(manifest.root_config),
                "pythia8_data": str(manifest.pythia8_data),
            },
        )
    ]

    linkage = manifest.payload.get("linkage_validation")
    linkage_ok = isinstance(linkage, dict) and bool(linkage) and all(
        isinstance(item, dict) and item.get("passed") is True
        for item in linkage.values()
    )

    for name in ("madgraph", "pythia8", "root", "delphes", "madanalysis5"):
        component = manifest.components[name]
        executable = manifest.executable(name)
        native = component["executables"].get("native")
        smoke = component["smoke_test"]
        owned = executable.resolve(strict=False).is_relative_to(
            manifest.stack_root.resolve(strict=False)
        )
        runnable = executable.is_file() and os.access(executable, os.X_OK)
        passed = owned and runnable and smoke.get("passed") is True and linkage_ok
        checks.append(
            DoctorCheck(
                check_id=f"managed_{name}",
                label=f"Managed {name} runtime",
                status=CheckStatus.PASS if passed else CheckStatus.FAILURE,
                summary=(
                    "Executable ownership, manifest version, recorded smoke test, and stack linkage agree."
                    if passed
                    else "Managed component ownership, smoke, or linkage validation failed."
                ),
                details={
                    "expected_path": str(executable),
                    "resolved_executable": str(executable.resolve(strict=False)),
                    "native_executable": native,
                    "version": component["version"],
                    "installation_ownership": owned,
                    "manifest_agreement": runnable,
                    "root_runtime_linkage": linkage_ok,
                    "smoke_test": smoke,
                },
                remediation=None if passed else "Rebuild only the failed clone-owned stack component and regenerate the manifest.",
            )
        )
    return checks
