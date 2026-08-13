#!/usr/bin/env python3
"""Audit manifest ownership and native HEP linkage without external discovery."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from hep_agent.runtime import (  # noqa: E402
    audit_managed_linkage,
    build_stack_environment,
    load_stack_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / ".hep-stack/manifest.json",
    )
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    manifest = load_stack_manifest(
        arguments.manifest,
        expected_repository_root=arguments.manifest.absolute().parent.parent,
    )
    environment = build_stack_environment(manifest)
    stack = manifest.stack_root.resolve()
    reports, failures = audit_managed_linkage(
        manifest,
        environment=environment,
    )

    root_values = {}
    for option in ("--prefix", "--bindir", "--libdir", "--version"):
        completed = subprocess.run(
            [str(manifest.root_config), option],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
            timeout=60,
        )
        if completed.returncode != 0:
            failures.append(f"root-config {option} failed")
        root_values[option] = completed.stdout.strip()
    if Path(root_values["--prefix"]).resolve() != manifest.root_prefix.resolve():
        failures.append("root-config prefix disagrees with manifest")

    payload = {
        "success": not failures,
        "installation_id": manifest.installation_id,
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "stack_root": str(stack),
        "executables": {name: str(path) for name, path in manifest.executables.items()},
        "pythia8_data": str(manifest.pythia8_data),
        "root_config": root_values,
        "linkage": reports,
        "failures": failures,
    }
    if arguments.json:
        print(json.dumps(payload, indent=2))
    else:
        for name, report in reports.items():
            print(
                f"{name}: {'PASS' if report['passed'] else 'FAIL'} "
                f"({report['tool']}) · {report['target']}"
            )
        print(f"PYTHIA8DATA: {manifest.pythia8_data}")
        print(f"ROOT: {root_values['--version']} · {root_values['--prefix']}")
        print("RESULT:", "PASS" if not failures else "FAIL")
        for failure in failures:
            print("  ", failure)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
