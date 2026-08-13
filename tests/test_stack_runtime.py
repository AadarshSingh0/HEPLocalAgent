"""Hermetic tests for the authoritative clone-owned HEP stack contract."""

from __future__ import annotations

import json
import os
import platform
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hep_agent.builders import MadGraphArtifact, MadGraphWorkflowArtifact
from hep_agent.execution import run_madgraph_workflow

from hep_agent.runtime import (
    STACK_MANIFEST_SCHEMA,
    StackConfigurationError,
    build_controlled_environment,
    build_stack_environment,
    load_stack_manifest,
    load_configured_stack,
)


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def create_manifest(repository: Path, installation_id: str = "test-install") -> Path:
    stack = repository / ".hep-stack"
    python = executable(repository / ".venv/bin/python")
    root_config = executable(stack / "root/bin/root-config")
    pythia_data = stack / "pythia8/share/Pythia8/xmldoc"
    pythia_data.mkdir(parents=True)
    library_paths = [
        stack / "root/lib",
        stack / "pythia8/lib",
        stack / "delphes",
    ]
    for item in library_paths:
        item.mkdir(parents=True, exist_ok=True)
    component_paths = {
        "madgraph": executable(stack / "madgraph/bin/mg5_aMC"),
        "pythia8": executable(stack / "pythia8/bin/pythia8-config"),
        "root": root_config,
        "delphes": executable(stack / "delphes/DelphesHepMC3"),
        "madanalysis5": executable(stack / "madanalysis5/bin/ma5"),
    }
    payload = {
        "schema_version": STACK_MANIFEST_SCHEMA,
        "installation_id": installation_id,
        "repository_root": str(repository),
        "stack_root": str(stack),
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "python": {"prefix": str(repository / ".venv"), "executable": str(python)},
        "runtime": {
            "root_prefix": str(stack / "root"),
            "root_config": str(root_config),
            "pythia8_data": str(pythia_data),
            "library_paths": [str(item) for item in library_paths],
        },
        "components": {},
        "ownership": {"installation_id": installation_id, "boundary": str(stack)},
    }
    for name, primary in component_paths.items():
        payload["components"][name] = {
            "version": "1.2.3",
            "source": {"url": f"https://example.invalid/{name}.tar.gz", "sha256": "a" * 64},
            "prefix": str(primary.parent.parent if name not in {"delphes"} else primary.parent),
            "executables": {"primary": str(primary), "native": str(primary)},
            "smoke_test": {"passed": True, "command": [str(primary)]},
        }
    payload["linkage_validation"] = {
        "delphes": {
            "passed": True,
            "tool": "ldd",
            "target": str(component_paths["delphes"]),
            "output": [f"libCore.so => {stack}/root/lib/libCore.so"],
        }
    }
    path = stack / "manifest.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


class StackRuntimeTests(unittest.TestCase):
    def test_poisoned_environment_is_replaced_by_managed_stack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "clone"
            path = create_manifest(repository)
            fake_python = repository / ".venv/bin/python"
            with patch("hep_agent.runtime.stack.sys.executable", str(fake_python)):
                manifest = load_stack_manifest(path, expected_repository_root=repository)
                environment = build_stack_environment(
                    manifest,
                    inherited={
                        "HOME": "/safe/home",
                        "PATH": "/snap/bin:/opt/homebrew/bin:/opt/root/bin:/fake",
                        "ROOTSYS": "/opt/root",
                        "PYTHIA8DATA": "/old/pythia/xmldoc",
                        "LD_LIBRARY_PATH": "/opt/root/lib:/old/lib",
                        "DYLD_LIBRARY_PATH": "/opt/homebrew/root/lib",
                        "PYTHONPATH": "/old/clone/.venv/lib",
                        "VIRTUAL_ENV": "/old/clone/.venv",
                        "CONDA_PREFIX": "/old/conda",
                        "CONDA_DEFAULT_ENV": "base",
                        "CONDA_SHLVL": "2",
                        "ROOT_INCLUDE_PATH": "/usr/include/root",
                        "LIBRARY_PATH": "/external/lib",
                        "CPATH": "/external/include",
                        "PKG_CONFIG_PATH": "/external/pkgconfig",
                    },
                )
            self.assertEqual(environment["HOME"], "/safe/home")
            self.assertEqual(environment["ROOTSYS"], str(repository / ".hep-stack/root"))
            self.assertEqual(
                environment["PYTHIA8DATA"],
                str(repository / ".hep-stack/pythia8/share/Pythia8/xmldoc"),
            )
            for hostile in ("/snap", "/opt/root", "/opt/homebrew", "/old/conda", "/old/clone"):
                self.assertNotIn(hostile, "\n".join(environment.values()))
            self.assertNotIn("CONDA_PREFIX", environment)
            self.assertNotIn("DYLD_LIBRARY_PATH", environment)
            self.assertTrue(environment["PATH"].startswith(str(repository / ".hep-stack/launchers")))
            layout_environment = build_controlled_environment(
                repository_root=manifest.repository_root,
                stack_root=manifest.stack_root,
                python_prefix=manifest.python_prefix,
                root_prefix=manifest.root_prefix,
                pythia8_data=manifest.pythia8_data,
                library_paths=manifest.library_paths,
                executable_directories=tuple(
                    dict.fromkeys(
                        path.parent for path in manifest.executables.values()
                    )
                ),
                inherited={
                    "PATH": "/snap/bin:/opt/root/bin",
                    "ROOTSYS": "/opt/root",
                    "CONDA_PREFIX": "/old/conda",
                },
            )
            self.assertEqual(layout_environment["PATH"], environment["PATH"])
            self.assertEqual(layout_environment["ROOTSYS"], environment["ROOTSYS"])

    def test_manifest_cannot_select_external_component_or_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "clone"
            path = create_manifest(repository)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["runtime"]["root_prefix"] = "/opt/root"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch("hep_agent.runtime.stack.sys.executable", str(repository / ".venv/bin/python")):
                with self.assertRaisesRegex(StackConfigurationError, "disagree|escapes managed stack"):
                    load_stack_manifest(path, expected_repository_root=repository)

    def test_manifest_from_previous_clone_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            clone_a = parent / "clone-a"
            clone_b = parent / "clone-b"
            manifest_a = create_manifest(clone_a, "clone-a-install")
            create_manifest(clone_b, "clone-b-install")
            with patch("hep_agent.runtime.stack.sys.executable", str(clone_b / ".venv/bin/python")):
                with self.assertRaisesRegex(StackConfigurationError, "different repository clone"):
                    load_stack_manifest(manifest_a, expected_repository_root=clone_b)

    def test_shared_launcher_outside_stack_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "clone"
            path = create_manifest(repository)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["components"]["madgraph"]["executables"]["primary"] = str(
                executable(Path(temporary) / "shared/bin/mg5")
            )
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch("hep_agent.runtime.stack.sys.executable", str(repository / ".venv/bin/python")):
                with self.assertRaisesRegex(StackConfigurationError, "escapes managed stack"):
                    load_stack_manifest(path, expected_repository_root=repository)

    def test_clone_launcher_cannot_dispatch_to_external_native_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "clone"
            path = create_manifest(repository)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["components"]["madgraph"]["executables"]["native"] = str(
                executable(Path(temporary) / "external/bin/mg5_aMC")
            )
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch(
                "hep_agent.runtime.stack.sys.executable",
                str(repository / ".venv/bin/python"),
            ):
                with self.assertRaisesRegex(
                    StackConfigurationError,
                    "escapes managed stack",
                ):
                    load_stack_manifest(path, expected_repository_root=repository)

    def test_altered_schema_and_failed_smoke_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "clone"
            path = create_manifest(repository)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["components"]["root"]["smoke_test"]["passed"] = False
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch("hep_agent.runtime.stack.sys.executable", str(repository / ".venv/bin/python")):
                with self.assertRaisesRegex(StackConfigurationError, "has not passed"):
                    load_stack_manifest(path, expected_repository_root=repository)

    def test_configured_paths_must_exactly_agree_with_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "clone"
            manifest_path = create_manifest(repository)
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            config = repository / "configs/local_paths.json"
            config.parent.mkdir(parents=True)
            config_payload = {
                "stack_manifest": str(manifest_path),
                "mg5_executable": payload["components"]["madgraph"]["executables"]["primary"],
                "madanalysis5_executable": payload["components"]["madanalysis5"]["executables"]["primary"],
                "pythia8_path": payload["components"]["pythia8"]["prefix"],
                "delphes_path": payload["components"]["delphes"]["prefix"],
                "root_prefix": payload["runtime"]["root_prefix"],
            }
            config.write_text(json.dumps(config_payload), encoding="utf-8")
            fake_python = repository / ".venv/bin/python"
            with patch("hep_agent.runtime.stack.sys.executable", str(fake_python)):
                manifest = load_configured_stack(
                    config, expected_repository_root=repository
                )
            self.assertEqual(manifest.path, manifest_path)

            config_payload["root_prefix"] = "/opt/root"
            config.write_text(json.dumps(config_payload), encoding="utf-8")
            with patch("hep_agent.runtime.stack.sys.executable", str(fake_python)):
                with self.assertRaisesRegex(
                    StackConfigurationError, "disagrees with managed stack"
                ):
                    load_configured_stack(config, expected_repository_root=repository)

    def test_wrong_root_native_linkage_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "clone"
            path = create_manifest(repository)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["linkage_validation"]["delphes"]["output"] = [
                "libCore.so => /opt/root/lib/libCore.so"
            ]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch("hep_agent.runtime.stack.sys.executable", str(repository / ".venv/bin/python")):
                with self.assertRaisesRegex(StackConfigurationError, "outside managed stack"):
                    load_stack_manifest(path, expected_repository_root=repository)

    def test_madgraph_runner_receives_common_sanitized_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "clone"
            manifest_path = create_manifest(repository)
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            mg5 = Path(payload["components"]["madgraph"]["executables"]["primary"])
            mg5.write_text(
                '''#!/bin/sh
printf '%s\n' "$PATH|$ROOTSYS|$PYTHIA8DATA|$LD_LIBRARY_PATH|${CONDA_PREFIX-unset}|${PYTHONPATH-unset}"
''',
                encoding="utf-8",
            )
            mg5.chmod(0o755)
            artifact = MadGraphWorkflowArtifact(
                process_artifact=MadGraphArtifact(commands=("import model sm", "generate e+ e- > mu+ mu-")),
                launch_commands=(),
            )
            inherited = {
                "PATH": "/snap/bin:/opt/root/bin:/opt/homebrew/bin",
                "ROOTSYS": "/opt/root",
                "PYTHIA8DATA": "/fake/xml",
                "LD_LIBRARY_PATH": "/opt/root/lib",
                "CONDA_PREFIX": "/old/conda",
                "PYTHONPATH": "/old/clone/.venv/lib",
            }
            with patch.dict(os.environ, inherited, clear=True), patch(
                "hep_agent.runtime.stack.sys.executable", str(repository / ".venv/bin/python")
            ):
                result = run_madgraph_workflow(
                    artifact, mg5_executable=mg5, run_directory=repository / "run",
                    stack_manifest=manifest_path, timeout_seconds=5,
                )
            self.assertTrue(result.success, result.failure_message)
            output = result.stdout_path.read_text(encoding="utf-8")
            self.assertIn(str(repository / ".hep-stack/root"), output)
            self.assertIn(str(repository / ".hep-stack/pythia8/share/Pythia8/xmldoc"), output)
            for hostile in ("/snap", "/opt/root", "/opt/homebrew", "/old/conda", "/old/clone"):
                self.assertNotIn(hostile, output)
            self.assertTrue(output.rstrip().endswith("unset|unset"))


    def test_every_public_entrypoint_requires_the_shared_stack_contract(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        expectations = {
            "src/hep_agent/ui/cli.py": (
                "load_configured_stack(",
                "stack_manifest=stack_manifest",
            ),
            "src/hep_agent/ui/web_app.py": (
                "load_configured_stack(",
                "stack_manifest=STACK_MANIFEST_PATH",
            ),
            "src/hep_agent/selftest.py": (
                "load_configured_stack(",
                "stack_manifest=stack_manifest",
            ),
            "src/hep_agent/doctor/checks.py": (
                "build_stack_environment(",
                "if managed_environment is None:",
            ),
            "scripts/finalize_managed_stack.py": (
                "build_controlled_environment(",
                '"madanalysis5_path": "None"',
            ),
        }
        for relative, required_text in expectations.items():
            source = (repository / relative).read_text(encoding="utf-8")
            for text in required_text:
                self.assertIn(text, source, relative)
        launcher = (repository / "scripts/run_managed_agent.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("/usr/local", launcher)


if __name__ == "__main__":
    unittest.main()
