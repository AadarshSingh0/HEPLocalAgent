#!/usr/bin/env python3
"""Pin an existing MadAnalysis 5 installation to managed dependencies."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import tempfile
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ma5", required=True, type=Path)
    parser.add_argument("--root-bindir", required=True, type=Path)
    parser.add_argument("--delphes-root", type=Path)
    return parser


def _validated_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"{label} does not exist: {resolved}")
    return resolved


def _replace_option(text: str, key: str, value: str) -> str:
    replacement = f"{key} = {value}"
    pattern = re.compile(
        rf"^[ \t]*#?[ \t]*{re.escape(key)}[ \t]*=.*$",
        re.MULTILINE,
    )
    if pattern.search(text) is None:
        return text.rstrip() + "\n" + replacement + "\n"

    replaced = False

    def replace(match: re.Match[str]) -> str:
        del match
        nonlocal replaced
        if replaced:
            return ""
        replaced = True
        return replacement

    return pattern.sub(replace, text)


def configure_runtime(
    *,
    ma5_executable: Path,
    root_bindir: Path,
    delphes_root: Path | None,
) -> tuple[Path, bool]:
    ma5 = _validated_file(ma5_executable, "MadAnalysis executable")
    root_config = _validated_file(
        root_bindir.expanduser().resolve() / "root-config",
        "root-config",
    )
    root_bindir = root_config.parent

    ma5_root = ma5.parent.parent
    options_path = ma5_root / "madanalysis/input/installation_options.dat"
    if not options_path.is_file():
        raise ValueError(
            f"MadAnalysis installation options do not exist: {options_path}"
        )

    options = {
        "root_veto": "0",
        "root_bin_path": str(root_bindir),
    }

    if delphes_root is not None:
        delphes = delphes_root.expanduser().resolve()
        _validated_file(
            delphes / "modules/ParticlePropagator.h",
            "Delphes header",
        )
        _validated_file(delphes / "libDelphes.so", "Delphes library")
        options.update(
            {
                "delphes_veto": "0",
                "delphes_includes": str(delphes),
                "delphes_libs": str(delphes),
            }
        )

    original = options_path.read_text(encoding="utf-8")
    updated = original
    for key, value in options.items():
        updated = _replace_option(updated, key, value)

    if updated == original:
        return options_path, False

    backup_path = options_path.with_name(
        options_path.name + ".before_hep_agent"
    )
    if not backup_path.exists():
        shutil.copy2(options_path, backup_path)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=options_path.name + ".",
        dir=options_path.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(updated)
        os.replace(temporary_name, options_path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise

    return options_path, True


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        path, changed = configure_runtime(
            ma5_executable=arguments.ma5,
            root_bindir=arguments.root_bindir,
            delphes_root=arguments.delphes_root,
        )
    except (OSError, ValueError) as exc:
        print(f"MadAnalysis runtime configuration failed: {exc}")
        return 1

    action = "Updated" if changed else "Verified"
    print(f"{action} MadAnalysis runtime options: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
