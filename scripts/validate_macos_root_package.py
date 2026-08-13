#!/usr/bin/env python3
"""Fail-closed validation of the exact ROOT package selected by Conda."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class RootPackagePlan:
    architecture: str
    version: str
    build: str
    archive: str
    sha256: str
    subdir: str

    @property
    def match_spec(self) -> str:
        return f"root_base={self.version}={self.build}"


ROOT_PACKAGE_PLANS = {
    "arm64": RootPackagePlan(
        architecture="arm64",
        version="6.40.02",
        build="cxx20_h17fc236_2",
        archive="root_base-6.40.02-cxx20_h17fc236_2.conda",
        sha256="051cd5227127a5042837c56f64ae98652febf54b06bba1f7cac9dcf2850be497",
        subdir="osx-arm64",
    ),
    "x86_64": RootPackagePlan(
        architecture="x86_64",
        version="6.40.02",
        build="cxx23_h36fdf7c_2",
        archive="root_base-6.40.02-cxx23_h36fdf7c_2.conda",
        sha256="96150f5f313adccf584d46bb26acb73033f7b9ffe30b866a923281464302cf46",
        subdir="osx-64",
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_root_package(
    *,
    architecture: str,
    runtime_root: Path,
    downloads: Path,
    package_cache: Path,
) -> dict[str, object]:
    try:
        plan = ROOT_PACKAGE_PLANS[architecture]
    except KeyError as error:
        raise ValueError(f"Unsupported Darwin architecture: {architecture}") from error

    downloaded = downloads / plan.archive
    if not downloaded.is_file():
        raise ValueError(f"Pinned ROOT archive is missing: {downloaded}")
    downloaded_sha = sha256_file(downloaded)
    if downloaded_sha != plan.sha256:
        raise ValueError(
            f"Pinned ROOT archive checksum mismatch: expected {plan.sha256}, "
            f"got {downloaded_sha}"
        )

    metadata_root = runtime_root / "conda-meta"
    records = []
    for path in sorted(metadata_root.glob("root_base-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read installed ROOT metadata {path}: {error}") from error
        if payload.get("name") == "root_base":
            records.append((path, payload))
    if len(records) != 1:
        raise ValueError(
            f"Expected exactly one installed root_base record, found {len(records)}"
        )

    metadata_path, record = records[0]
    required = {
        "name": "root_base",
        "version": plan.version,
        "build": plan.build,
    }
    for field, expected in required.items():
        if record.get(field) != expected:
            raise ValueError(
                f"Installed ROOT {field} mismatch in {metadata_path}: "
                f"expected {expected!r}, got {record.get(field)!r}"
            )
    metadata_sha = record.get("sha256")
    if metadata_sha is not None and metadata_sha != plan.sha256:
        raise ValueError(
            f"Installed ROOT sha256 mismatch in {metadata_path}: "
            f"expected {plan.sha256!r}, got {metadata_sha!r}"
        )
    if record.get("subdir") not in (None, plan.subdir):
        raise ValueError(
            f"Installed ROOT subdir mismatch: expected {plan.subdir!r}, "
            f"got {record.get('subdir')!r}"
        )
    filename = record.get("fn")
    if filename is not None and filename != plan.archive:
        raise ValueError(
            f"Installed ROOT artifact mismatch: expected {plan.archive!r}, got {filename!r}"
        )
    url = record.get("url")
    if isinstance(url, str) and Path(urlparse(url).path).name != plan.archive:
        raise ValueError(f"Installed ROOT URL does not select {plan.archive}: {url}")

    cached = package_cache / plan.archive
    if not cached.is_file():
        raise ValueError(f"Verified ROOT package cache artifact is missing: {cached}")
    cached_sha = sha256_file(cached)
    if cached_sha != plan.sha256:
        raise ValueError(
            f"ROOT package cache checksum mismatch: expected {plan.sha256}, "
            f"got {cached_sha}"
        )

    return {
        "name": record["name"],
        "version": record["version"],
        "build": record["build"],
        "archive": plan.archive,
        "sha256": plan.sha256,
        "metadata": str(metadata_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--architecture", required=True, choices=sorted(ROOT_PACKAGE_PLANS))
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--downloads", required=True, type=Path)
    parser.add_argument("--package-cache", required=True, type=Path)
    arguments = parser.parse_args()
    result = validate_root_package(
        architecture=arguments.architecture,
        runtime_root=arguments.runtime_root,
        downloads=arguments.downloads,
        package_cache=arguments.package_cache,
    )
    print(
        "Validated installed ROOT package: "
        f"{result['name']}={result['version']}={result['build']} "
        f"sha256={result['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
