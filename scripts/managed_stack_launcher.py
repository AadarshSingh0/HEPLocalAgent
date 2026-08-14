#!/usr/bin/env python3
"""Clone-local launcher that cannot inherit or discover external HEP tools."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    launcher = Path(__file__).resolve()
    stack_root = launcher.parent.parent
    repository_root = stack_root.parent
    sys.path.insert(0, str(repository_root / "src"))

    from hep_agent.runtime import build_stack_environment, load_stack_manifest

    manifest = load_stack_manifest(
        stack_root / "manifest.json",
        expected_repository_root=repository_root,
    )
    component = launcher.name
    native = manifest.components[component]["executables"].get("native")
    if not isinstance(native, str):
        raise SystemExit(f"Manifest has no native executable for {component!r}.")
    environment = build_stack_environment(manifest)
    os.execve(native, [native, *sys.argv[1:]], environment)


if __name__ == "__main__":
    main()
