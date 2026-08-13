#!/usr/bin/env python3
"""Configure, smoke-test, and record one freshly built clone-owned HEP stack."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
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
)


SOURCES = {
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
    "root": (
        "6.40.02",
        "https://root.cern/download/root_v6.40.02.Linux-ubuntu24.04-x86_64-gcc13.3.tar.gz",
        "127db12fa498b51ce89e242bc787d7ed24dfe4cee935783ed13d39e7969eb486",
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


def controlled_environment() -> dict[str, str]:
    root = STACK_ROOT / "root"
    pythia = STACK_ROOT / "pythia8"
    hepmc = STACK_ROOT / "hepmc2"
    return build_controlled_environment(
        repository_root=PROJECT_ROOT,
        stack_root=STACK_ROOT,
        python_prefix=PROJECT_ROOT / ".venv",
        root_prefix=root,
        pythia8_data=pythia / "share/Pythia8/xmldoc",
        library_paths=(
            root / "lib",
            pythia / "lib",
            hepmc / "lib",
            STACK_ROOT / "delphes",
            STACK_ROOT / "madanalysis5/tools/SampleAnalyzer/Lib",
        ),
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
    (LOG_ROOT / log_name).write_text(
        completed.stdout + "\n--- STDERR ---\n" + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}); see {LOG_ROOT / log_name}")
    return completed.stdout


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

    # GitHub source archives omit the release-generated metadata required by
    # both MG5 and MA5 embedded integration. Keep it deterministic and pinned.
    (STACK_ROOT / "madanalysis5/version.txt").write_text(
        "MA5 version : 1.11.0\nDate : 2025-04-24\n",
        encoding="utf-8",
    )

    configure_runtime(
        ma5_executable=STACK_ROOT / "madanalysis5/bin/ma5",
        root_bindir=STACK_ROOT / "root/bin",
        delphes_root=STACK_ROOT / "delphes",
    )


def write_launcher(component: str) -> Path:
    destination = STACK_ROOT / "launchers" / component
    source = PROJECT_ROOT / "scripts/managed_stack_launcher.py"
    text = source.read_text(encoding="utf-8")
    text = text.replace("#!/usr/bin/env python3", f"#!{PROJECT_ROOT / '.venv/bin/python'}", 1)
    destination.write_text(text, encoding="utf-8")
    destination.chmod(0o755)
    return destination


def ldd_validation(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        ["/usr/bin/ldd", str(path)], capture_output=True, text=True, check=False,
        env=controlled_environment(),
    )
    output = completed.stdout + completed.stderr
    bad_lines = []
    hep_names = ("root", "pythia", "hepmc", "delphes")
    for line in output.splitlines():
        lowered = line.lower()
        if any(name in lowered for name in hep_names) and str(STACK_ROOT).lower() not in lowered:
            bad_lines.append(line.strip())
    if completed.returncode != 0 or bad_lines or "not found" in output:
        raise RuntimeError(f"Unsafe linkage for {path}: {bad_lines or output.strip()}")
    return {"passed": True, "tool": "ldd", "target": str(path), "output": output.splitlines()}


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
        "root": STACK_ROOT / "root/bin/root-config",
        "delphes": STACK_ROOT / "delphes/DelphesHepMC2",
        "madanalysis5": STACK_ROOT / "madanalysis5/bin/ma5",
    }
    for label, path in native.items():
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"Fresh {label} executable is missing: {path}")

    mg5_script = LOG_ROOT / "madgraph-smoke.mg5"
    mg5_script.write_text("import model sm\ndisplay particles\nquit\n", encoding="utf-8")
    mg5_output = run(
        [str(python), str(native["madgraph"]), str(mg5_script)],
        "madgraph-smoke.log",
    )
    if "MadGraph5_aMC" not in mg5_output:
        raise RuntimeError(f"MadGraph smoke failed; see {LOG_ROOT / 'madgraph-smoke.log'}")
    root_output = run([str(native["root"]), "--version"], "root-smoke-final.log")
    pythia_output = run([str(native["pythia8"]), "--version"], "pythia8-smoke-final.log")
    ma5_script = LOG_ROOT / "ma5-smoke.ma5"
    ma5_script.write_text("quit\n", encoding="utf-8")
    ma5_output = run(
        [str(python), str(native["madanalysis5"]), "-H", "-f", "-s", str(ma5_script)],
        "madanalysis5-smoke.log",
    )
    if "MA5-ERROR" in ma5_output or "MA5 release" not in ma5_output:
        raise RuntimeError(f"MadAnalysis smoke failed; see {LOG_ROOT / 'madanalysis5-smoke.log'}")

    linkages = {
        "delphes": ldd_validation(native["delphes"]),
        "libDelphes": ldd_validation(STACK_ROOT / "delphes/libDelphes.so"),
        "mg5amc_py8_interface": ldd_validation(
            STACK_ROOT / "mg5amc_py8_interface/MG5aMC_PY8_interface"
        ),
        "ma5_root": ldd_validation(
            STACK_ROOT / "madanalysis5/tools/SampleAnalyzer/Lib/libroot_for_ma5.so"
        ),
        "ma5_delphes": ldd_validation(
            STACK_ROOT / "madanalysis5/tools/SampleAnalyzer/Lib/libdelphes_for_ma5.so"
        ),
    }

    launchers = {
        "madgraph": write_launcher("madgraph"),
        "madanalysis5": write_launcher("madanalysis5"),
    }
    prefixes = {
        "madgraph": STACK_ROOT / "madgraph",
        "pythia8": STACK_ROOT / "pythia8",
        "root": STACK_ROOT / "root",
        "delphes": STACK_ROOT / "delphes",
        "madanalysis5": STACK_ROOT / "madanalysis5",
    }
    smoke_outputs = {
        "madgraph": mg5_output,
        "pythia8": pythia_output,
        "root": root_output,
        "delphes": "Built executable and validated managed ROOT linkage.",
        "madanalysis5": ma5_output,
    }
    installation_id = str(uuid.uuid4())
    components: dict[str, object] = {}
    for name, (version, url, sha256) in SOURCES.items():
        primary = launchers.get(name, native[name])
        components[name] = {
            "version": version,
            "source": {"url": url, "sha256": sha256},
            "prefix": str(prefixes[name]),
            "executables": {"primary": str(primary), "native": str(native[name])},
            "smoke_test": {
                "passed": True,
                "log": str(LOG_ROOT / f"{name.replace('madanalysis5', 'madanalysis5')}-smoke.log"),
                "summary": smoke_outputs[name][-1000:],
            },
        }

    manifest = {
        "schema_version": STACK_MANIFEST_SCHEMA,
        "installation_id": installation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(PROJECT_ROOT),
        "stack_root": str(STACK_ROOT),
        "platform": {"system": platform.system(), "machine": platform.machine(), "release": platform.release()},
        "python": {"prefix": str(PROJECT_ROOT / ".venv"), "executable": str(python), "version": platform.python_version()},
        "runtime": {
            "root_prefix": str(STACK_ROOT / "root"),
            "root_config": str(native["root"]),
            "pythia8_data": str(STACK_ROOT / "pythia8/share/Pythia8/xmldoc"),
            "library_paths": [
                str(STACK_ROOT / "root/lib"), str(STACK_ROOT / "pythia8/lib"),
                str(STACK_ROOT / "hepmc2/lib"), str(STACK_ROOT / "delphes"),
                str(STACK_ROOT / "madanalysis5/tools/SampleAnalyzer/Lib"),
            ],
        },
        "components": components,
        "support_components": {
            "hepmc2": {
                "version": "2.06.11", "prefix": str(STACK_ROOT / "hepmc2"),
                "source": {
                    "url": "https://hepmc.web.cern.ch/hepmc/releases/hepmc2.06.11.tgz",
                    "sha256": "86b66ea0278f803cde5774de8bd187dd42c870367f1cbf6cdaec8dc7cf6afc10",
                },
            },
            "mg5amc_py8_interface": {
                "version": "1.3", "prefix": str(STACK_ROOT / "mg5amc_py8_interface"),
                "source": {
                    "url": "https://madgraph.mi.infn.it/Downloads/MG5aMC_PY8_interface/MG5aMC_PY8_interface_V1.3.tar.gz",
                    "sha256": "1a7a62e96207701f9a8a44fec01426b7f474b580ba2c4fbb82ecd0d83fcea332",
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
        "root_prefix": str(STACK_ROOT / "root"),
    }
    config_path = PROJECT_ROOT / "configs/local_paths.json"
    config_path.write_text(json.dumps(local_paths, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote authoritative managed stack manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
