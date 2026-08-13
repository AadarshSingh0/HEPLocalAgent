#!/usr/bin/env python3
"""Audit manifest ownership and native HEP linkage without external discovery."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from hep_agent.runtime import build_stack_environment, load_stack_manifest  # noqa: E402


def is_elf(path: Path) -> bool:
    try:
        return path.read_bytes()[:4] == b"\x7fELF"
    except OSError:
        return False


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

    targets = {
        "root": manifest.root_prefix / "bin/root.exe",
        "pythia8": Path(manifest.components["pythia8"]["prefix"]) / "lib/libpythia8.so",
        "hepmc2": stack / "hepmc2/lib/libHepMC.so",
        "delphes": stack / "delphes/DelphesHepMC2",
        "libDelphes": stack / "delphes/libDelphes.so",
        "mg5amc_py8_interface": stack / "mg5amc_py8_interface/MG5aMC_PY8_interface",
        "ma5_root": stack / "madanalysis5/tools/SampleAnalyzer/Lib/libroot_for_ma5.so",
        "ma5_delphes": stack / "madanalysis5/tools/SampleAnalyzer/Lib/libdelphes_for_ma5.so",
        "ma5_test_root": stack / "madanalysis5/tools/SampleAnalyzer/Bin/TestRoot",
        "ma5_test_delphes": stack / "madanalysis5/tools/SampleAnalyzer/Bin/TestDelphes",
    }
    failures: list[str] = []
    reports: dict[str, object] = {}
    hep_library_names = (
        "libcore", "libtree", "libroot", "libpythia", "libhepmc", "libdelphes"
    )

    for name, raw_target in targets.items():
        target = Path(raw_target).resolve(strict=False)
        if not target.is_relative_to(stack):
            failures.append(f"{name}: target escapes managed stack: {target}")
            continue
        if not target.is_file() or not is_elf(target):
            failures.append(f"{name}: missing ELF target: {target}")
            continue
        completed = subprocess.run(
            ["/usr/bin/ldd", str(target)],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        output = completed.stdout + completed.stderr
        target_failures: list[str] = []
        if completed.returncode != 0 or "not found" in output:
            target_failures.append("ldd failed or reported a missing library")
        for line in output.splitlines():
            lowered = line.lower()
            if not any(library in lowered for library in hep_library_names):
                continue
            absolute = [
                Path(token)
                for token in line.replace("=>", " ").split()
                if token.startswith("/")
            ]
            for resolved in absolute:
                if not resolved.resolve(strict=False).is_relative_to(stack):
                    target_failures.append(
                        f"HEP library resolves outside stack: {line.strip()}"
                    )
        if target_failures:
            failures.extend(f"{name}: {failure}" for failure in target_failures)
        reports[name] = {
            "target": str(target),
            "passed": not target_failures,
            "ldd": output.splitlines(),
        }

    root_values = {}
    for option in ("--prefix", "--bindir", "--libdir", "--version"):
        completed = subprocess.run(
            [str(manifest.root_config), option],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        if completed.returncode != 0:
            failures.append(f"root-config {option} failed")
        root_values[option] = completed.stdout.strip()
    if Path(root_values["--prefix"]).resolve() != manifest.root_prefix.resolve():
        failures.append("root-config prefix disagrees with manifest")

    payload = {
        "success": not failures,
        "installation_id": manifest.installation_id,
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
            print(f"{name}: {'PASS' if report['passed'] else 'FAIL'} · {report['target']}")
        print(f"PYTHIA8DATA: {manifest.pythia8_data}")
        print(f"ROOT: {root_values['--version']} · {root_values['--prefix']}")
        print("RESULT:", "PASS" if not failures else "FAIL")
        for failure in failures:
            print("  ", failure)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
