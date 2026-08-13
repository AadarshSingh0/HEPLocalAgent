#!/usr/bin/env python3
"""Configure, smoke-test, audit, and record one clone-owned HEP stack."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STACK_ROOT = PROJECT_ROOT / ".hep-stack"
LOG_ROOT = STACK_ROOT / "logs"
SOURCE_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from hep_agent.runtime import (  # noqa: E402
    STACK_MANIFEST_SCHEMA,
    build_controlled_environment,
    inspect_native_linkage,
)


COMMON_SOURCES = {
    "madgraph": (
        "3.5.13",
        "https://github.com/mg5amcnlo/mg5amcnlo/archive/refs/tags/v3.5.13.tar.gz",
        "0c75437481cc7808b59b578bc454d2c7bc12721b8bd848a287f35503202fabe7",
    ),
    "pythia8": (
        "8.317",
        "https://pythia.org/releases/pythia83/pythia8317.tgz",
        "1ae551d14dac495ddfe6b344792035ebe410fe6c6004d44a335e0ece0e745adf",
    ),
    "delphes": (
        "3.5.1",
        "https://github.com/delphes/delphes/archive/refs/tags/3.5.1.tar.gz",
        "b60d26d2ee2c84b58fbf2cf397fabd0ef3e89d3a0546d843c4ada82cc802d787",
    ),
    "madanalysis5": (
        "1.11.0",
        "https://github.com/MadAnalysis/madanalysis5/archive/refs/tags/v1.11.0.tar.gz",
        "6d2e73ae6d7d71cffa12c7184e8b243e1260e2f1d8e784edbf3058d6fc4b5351",
    ),
}
LINUX_ROOT_SOURCE = (
    "6.40.02",
    "https://root.cern/download/root_v6.40.02.Linux-ubuntu24.04-x86_64-gcc13.3.tar.gz",
    "127db12fa498b51ce89e242bc787d7ed24dfe4cee935783ed13d39e7969eb486",
)
DARWIN_ROOT_SOURCES = {
    "arm64": (
        "6.40.02",
        "https://conda.anaconda.org/conda-forge/osx-arm64/root_base-6.40.02-cxx20_h17fc236_2.conda",
        "051cd5227127a5042837c56f64ae98652febf54b06bba1f7cac9dcf2850be497",
    ),
    "x86_64": (
        "6.40.02",
        "https://conda.anaconda.org/conda-forge/osx-64/root_base-6.40.02-cxx23_h36fdf7c_2.conda",
        "96150f5f313adccf584d46bb26acb73033f7b9ffe30b866a923281464302cf46",
    ),
}
MINIFORGE_SOURCES = {
    "arm64": {
        "version": "26.3.2-2",
        "url": "https://github.com/conda-forge/miniforge/releases/download/26.3.2-2/Miniforge3-26.3.2-2-MacOSX-arm64.sh",
        "sha256": "2657d94152343cff7c06159ac9fc09624d7879fa9575c5a0a324c571c4df0ade",
    },
    "x86_64": {
        "version": "26.3.2-2",
        "url": "https://github.com/conda-forge/miniforge/releases/download/26.3.2-2/Miniforge3-26.3.2-2-MacOSX-x86_64.sh",
        "sha256": "a755192103de19bb2782685ac78820c2e00702e5f33e6e4f0a3bf3c214f45d69",
    },
}


def is_darwin() -> bool:
    return platform.system() == "Darwin"


def root_prefix() -> Path:
    return STACK_ROOT / ("runtime" if is_darwin() else "root")


def root_source() -> tuple[str, str, str]:
    if not is_darwin():
        return LINUX_ROOT_SOURCE
    try:
        return DARWIN_ROOT_SOURCES[platform.machine()]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported Darwin architecture: {platform.machine()}") from exc


def library_paths() -> tuple[Path, ...]:
    root = root_prefix()
    pythia = STACK_ROOT / "pythia8"
    hepmc = STACK_ROOT / "hepmc2"
    common = (
        pythia / "lib",
        root / "lib",
        hepmc / "lib",
        STACK_ROOT / "delphes",
        STACK_ROOT / "madanalysis5/tools/SampleAnalyzer/Lib",
    )
    if is_darwin():
        return common
    return (root / "lib", pythia / "lib", *common[2:])


def controlled_environment() -> dict[str, str]:
    pythia = STACK_ROOT / "pythia8"
    return build_controlled_environment(
        repository_root=PROJECT_ROOT,
        stack_root=STACK_ROOT,
        python_prefix=PROJECT_ROOT / ".venv",
        root_prefix=root_prefix(),
        pythia8_data=pythia / "share/Pythia8/xmldoc",
        library_paths=library_paths(),
        executable_directories=(
            STACK_ROOT / "madgraph/bin",
            pythia / "bin",
            STACK_ROOT / "delphes",
            STACK_ROOT / "madanalysis5/bin",
        ),
    )


def run(command: list[str], log_name: str, *, input_text: str | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=STACK_ROOT,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
        env=controlled_environment(),
    )
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    combined = completed.stdout + "\n--- STDERR ---\n" + completed.stderr
    (LOG_ROOT / log_name).write_text(combined, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}); see {LOG_ROOT / log_name}")
    return combined


def configure_mg5() -> Path:
    configuration = STACK_ROOT / "madgraph/input/mg5_configuration.txt"
    defaults = STACK_ROOT / "madgraph/input/.mg5_configuration_default.txt"
    text = defaults.read_text(encoding="utf-8")
    values = {
        "pythia8_path": STACK_ROOT / "pythia8",
        "mg5amc_py8_interface_path": STACK_ROOT / "mg5amc_py8_interface",
        "delphes_path": STACK_ROOT / "delphes",
        "madanalysis5_path": "None",
    }
    for key, value in values.items():
        text += f"\n{key} = {value}\n"
    configuration.write_text(text, encoding="utf-8")
    return configuration


def configure_ma5() -> None:
    from configure_madanalysis_runtime import configure_runtime

    (STACK_ROOT / "madanalysis5/version.txt").write_text(
        "MA5 version : 1.11.0\nDate : 2025-04-24\n",
        encoding="utf-8",
    )
    configure_runtime(
        ma5_executable=STACK_ROOT / "madanalysis5/bin/ma5",
        root_bindir=root_prefix() / "bin",
        delphes_root=STACK_ROOT / "delphes",
    )


def write_launcher(component: str) -> tuple[Path, str]:
    destination = STACK_ROOT / "launchers" / component
    source = PROJECT_ROOT / "scripts/managed_stack_launcher.py"
    text = source.read_text(encoding="utf-8")
    text = text.replace("#!/usr/bin/env python3", f"#!{PROJECT_ROOT / '.venv/bin/python'}", 1)
    destination.write_text(text, encoding="utf-8")
    destination.chmod(0o755)
    return destination, hashlib.sha256(text.encode("utf-8")).hexdigest()


def managed_library(directory: Path, stem: str) -> Path:
    candidates = (
        directory / f"{stem}.dylib",
        directory / f"{stem}.so",
        directory / f"{stem}.a",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"Missing managed library {stem} in {directory}")


def linkage_targets() -> dict[str, Path]:
    ma5_lib = STACK_ROOT / "madanalysis5/tools/SampleAnalyzer/Lib"
    return {
        "root": root_prefix() / "bin/root.exe",
        "pythia8": managed_library(STACK_ROOT / "pythia8/lib", "libpythia8"),
        "hepmc2": managed_library(STACK_ROOT / "hepmc2/lib", "libHepMC"),
        "delphes": STACK_ROOT / "delphes/DelphesHepMC2",
        "libDelphes": managed_library(STACK_ROOT / "delphes", "libDelphes"),
        "mg5amc_py8_interface": STACK_ROOT / "mg5amc_py8_interface/MG5aMC_PY8_interface",
        "ma5_root": managed_library(ma5_lib, "libroot_for_ma5"),
        "ma5_delphes": managed_library(ma5_lib, "libdelphes_for_ma5"),
        "ma5_test_root": STACK_ROOT / "madanalysis5/tools/SampleAnalyzer/Bin/TestRoot",
        "ma5_test_delphes": STACK_ROOT / "madanalysis5/tools/SampleAnalyzer/Bin/TestDelphes",
    }


def conda_packages() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    metadata = root_prefix() / "conda-meta"
    if not metadata.is_dir():
        return records
    for path in sorted(metadata.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        records.append(
            {
                key: payload[key]
                for key in ("name", "version", "build", "build_number", "channel", "url", "sha256")
                if key in payload
            }
        )
    return records


def runtime_provider() -> dict[str, object]:
    if not is_darwin():
        return {
            "kind": "clone-owned-native",
            "prefix": str(STACK_ROOT),
            "external_discovery": False,
        }
    miniforge = MINIFORGE_SOURCES[platform.machine()]
    return {
        "kind": "clone-owned-miniforge",
        "manager_prefix": str(STACK_ROOT / "miniforge"),
        "prefix": str(root_prefix()),
        "source": miniforge,
        "packages": conda_packages(),
        "external_discovery": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize", action="store_true")
    arguments = parser.parse_args()
    if not arguments.initialize:
        parser.error("--initialize is required for a freshly built stack")

    configure_mg5()
    configure_ma5()

    python = PROJECT_ROOT / ".venv/bin/python"
    native = {
        "madgraph": STACK_ROOT / "madgraph/bin/mg5_aMC",
        "pythia8": STACK_ROOT / "pythia8/bin/pythia8-config",
        "root": root_prefix() / "bin/root-config",
        "delphes": STACK_ROOT / "delphes/DelphesHepMC2",
        "madanalysis5": STACK_ROOT / "madanalysis5/bin/ma5",
    }
    for label, path in native.items():
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"Fresh {label} executable is missing: {path}")

    mg5_script = LOG_ROOT / "madgraph-smoke.mg5"
    mg5_script.write_text("import model sm\ndisplay particles\nquit\n", encoding="utf-8")
    mg5_output = run([str(python), str(native["madgraph"]), str(mg5_script)], "madgraph-smoke.log")
    if "MadGraph5_aMC" not in mg5_output:
        raise RuntimeError(f"MadGraph smoke failed; see {LOG_ROOT / 'madgraph-smoke.log'}")

    root_config_output = run([str(native["root"]), "--version"], "root-config-smoke.log")
    root_output = run(
        [str(root_prefix() / "bin/root"), "-l", "-b", "-q", "-e", "gROOT->GetVersion();"],
        "root-smoke.log",
    )
    pythia_output = run([str(native["pythia8"]), "--version"], "pythia8-smoke.log")

    ma5_script = LOG_ROOT / "ma5-smoke.ma5"
    ma5_script.write_text("quit\n", encoding="utf-8")
    ma5_output = run(
        [str(python), str(native["madanalysis5"]), "-H", "-f", "-s", str(ma5_script)],
        "madanalysis5-smoke.log",
    )
    if "MA5-ERROR" in ma5_output or "MA5 release" not in ma5_output:
        raise RuntimeError(f"MadAnalysis smoke failed; see {LOG_ROOT / 'madanalysis5-smoke.log'}")

    linkages: dict[str, object] = {}
    for name, target in linkage_targets().items():
        if not target.is_file():
            raise RuntimeError(f"Missing linkage target {name}: {target}")
        result = inspect_native_linkage(
            target,
            STACK_ROOT,
            environment=controlled_environment(),
            enforce_system_libcpp=is_darwin() and name == "pythia8",
        )
        if result.get("passed") is not True:
            raise RuntimeError(f"Unsafe linkage for {target}: {result.get('failures')}")
        linkages[name] = result

    launcher_records = {
        name: write_launcher(name) for name in ("madgraph", "madanalysis5")
    }
    launchers = {name: value[0] for name, value in launcher_records.items()}
    prefixes = {
        "madgraph": STACK_ROOT / "madgraph",
        "pythia8": STACK_ROOT / "pythia8",
        "root": root_prefix(),
        "delphes": STACK_ROOT / "delphes",
        "madanalysis5": STACK_ROOT / "madanalysis5",
    }
    sources = {**COMMON_SOURCES, "root": root_source()}
    smoke_outputs = {
        "madgraph": mg5_output,
        "pythia8": pythia_output,
        "root": root_config_output + root_output,
        "delphes": "Built executable and validated clone-owned ROOT linkage.",
        "madanalysis5": ma5_output,
    }
    smoke_logs = {
        "madgraph": "madgraph-smoke.log",
        "pythia8": "pythia8-smoke.log",
        "root": "root-smoke.log",
        "delphes": "delphes-build.log",
        "madanalysis5": "madanalysis5-smoke.log",
    }
    installation_id = str(uuid.uuid4())
    components: dict[str, object] = {}
    for name, (version, url, sha256) in sources.items():
        primary = launchers.get(name, native[name])
        component: dict[str, object] = {
            "version": version,
            "source": {"url": url, "sha256": sha256},
            "prefix": str(prefixes[name]),
            "executables": {"primary": str(primary), "native": str(native[name])},
            "smoke_test": {
                "passed": True,
                "log": str(LOG_ROOT / smoke_logs[name]),
                "summary": smoke_outputs[name][-1000:],
            },
        }
        if name in launcher_records:
            component["launcher_sha256"] = launcher_records[name][1]
        components[name] = component

    manifest = {
        "schema_version": STACK_MANIFEST_SCHEMA,
        "installation_id": installation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(PROJECT_ROOT),
        "stack_root": str(STACK_ROOT),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "release": platform.release(),
        },
        "python": {
            "prefix": str(PROJECT_ROOT / ".venv"),
            "executable": str(python),
            "version": platform.python_version(),
            "runtime_provider": runtime_provider(),
        },
        "runtime": {
            "root_prefix": str(root_prefix()),
            "root_config": str(native["root"]),
            "pythia8_data": str(STACK_ROOT / "pythia8/share/Pythia8/xmldoc"),
            "library_paths": [str(path) for path in library_paths()],
        },
        "components": components,
        "support_components": {
            "hepmc2": {
                "version": "2.06.11",
                "prefix": str(STACK_ROOT / "hepmc2"),
                "source": {
                    "url": "https://hepmc.web.cern.ch/hepmc/releases/hepmc2.06.11.tgz",
                    "sha256": "86b66ea0278f803cde5774de8bd187dd42c870367f1cbf6cdaec8dc7cf6afc10",
                },
                "build": {"compiler": "/usr/bin/clang++" if is_darwin() else "system", "shared": not is_darwin()},
                "artifact": str(
                    managed_library(STACK_ROOT / "hepmc2/lib", "libHepMC")
                ),
                "smoke_test": {
                    "passed": True,
                    "log": str(LOG_ROOT / "hepmc2-build.log"),
                },
            },
            "mg5amc_py8_interface": {
                "version": "1.3",
                "prefix": str(STACK_ROOT / "mg5amc_py8_interface"),
                "source": {
                    "url": "https://madgraph.mi.infn.it/Downloads/MG5aMC_PY8_interface/MG5aMC_PY8_interface_V1.3.tar.gz",
                    "sha256": "1a7a62e96207701f9a8a44fec01426b7f474b580ba2c4fbb82ecd0d83fcea332",
                },
                "executable": str(
                    STACK_ROOT / "mg5amc_py8_interface/MG5aMC_PY8_interface"
                ),
                "smoke_test": {
                    "passed": True,
                    "log": str(LOG_ROOT / "mg5amc-py8-interface-build.log"),
                },
            },
        },
        "linkage_validation": linkages,
        "ownership": {"installation_id": installation_id, "boundary": str(STACK_ROOT)},
    }
    manifest_path = STACK_ROOT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    local_paths = {
        "stack_manifest": str(manifest_path),
        "mg5_executable": str(launchers["madgraph"]),
        "madanalysis5_executable": str(launchers["madanalysis5"]),
        "pythia8_path": str(STACK_ROOT / "pythia8"),
        "delphes_path": str(STACK_ROOT / "delphes"),
        "root_prefix": str(root_prefix()),
    }
    config_path = PROJECT_ROOT / "configs/local_paths.json"
    config_path.write_text(json.dumps(local_paths, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote authoritative managed stack manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
