"""Hermetic Darwin coverage for the clone-owned managed HEP stack."""

from __future__ import annotations

import json
import hashlib
import os
import platform
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hep_agent.runtime import (
    STACK_MANIFEST_SCHEMA,
    StackConfigurationError,
    build_controlled_environment,
    load_stack_manifest,
    validate_macho_linkage,
)


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_macos_root_package import (  # noqa: E402
    ROOT_PACKAGE_PLANS,
    validate_root_package,
)


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def darwin_manifest(repository: Path, architecture: str) -> Path:
    stack = repository / ".hep-stack"
    python = executable(repository / ".venv/bin/python")
    runtime = stack / "runtime"
    root_config = executable(runtime / "bin/root-config")
    pythia_data = stack / "pythia8/share/Pythia8/xmldoc"
    pythia_data.mkdir(parents=True)
    libraries = [
        stack / "pythia8/lib",
        runtime / "lib",
        stack / "hepmc2/lib",
        stack / "delphes",
        stack / "madanalysis5/tools/SampleAnalyzer/Lib",
    ]
    for directory in libraries:
        directory.mkdir(parents=True, exist_ok=True)

    component_layout = {
        "madgraph": (stack / "madgraph", executable(stack / "madgraph/bin/mg5_aMC")),
        "pythia8": (stack / "pythia8", executable(stack / "pythia8/bin/pythia8-config")),
        "root": (runtime, root_config),
        "delphes": (stack / "delphes", executable(stack / "delphes/DelphesHepMC2")),
        "madanalysis5": (stack / "madanalysis5", executable(stack / "madanalysis5/bin/ma5")),
    }
    linkage_target = executable(stack / "delphes/DelphesHepMC2")
    root_plan = ROOT_PACKAGE_PLANS[architecture]
    payload: dict[str, object] = {
        "schema_version": STACK_MANIFEST_SCHEMA,
        "installation_id": f"darwin-{architecture}",
        "repository_root": str(repository),
        "stack_root": str(stack),
        "platform": {"system": "Darwin", "machine": architecture},
        "python": {
            "prefix": str(repository / ".venv"),
            "executable": str(python),
            "runtime_provider": {
                "kind": "clone-owned-miniforge",
                "manager_prefix": str(stack / "miniforge"),
                "prefix": str(runtime),
                "source": {
                    "version": "26.3.2-2",
                    "url": "https://example.invalid/miniforge.sh",
                    "sha256": "b" * 64,
                },
                "packages": [
                    {
                        "name": "root_base",
                        "version": root_plan.version,
                        "build": root_plan.build,
                        "sha256": root_plan.sha256,
                    }
                ],
                "external_discovery": False,
            },
        },
        "runtime": {
            "root_prefix": str(runtime),
            "root_config": str(root_config),
            "pythia8_data": str(pythia_data),
            "library_paths": [str(path) for path in libraries],
        },
        "components": {},
        "linkage_validation": {
            "delphes": {
                "passed": True,
                "tool": "otool",
                "target": str(linkage_target),
                "output": ["@rpath/libCore.6.40.so"],
                "resolved_paths": [str(runtime / "lib/libCore.6.40.so")],
            }
        },
        "ownership": {
            "installation_id": f"darwin-{architecture}",
            "boundary": str(stack),
        },
    }
    components = payload["components"]
    assert isinstance(components, dict)
    for name, (prefix, primary) in component_layout.items():
        components[name] = {
            "version": "1.2.3",
            "source": {
                "url": f"https://example.invalid/{name}.tar.gz",
                "sha256": "a" * 64,
            },
            "prefix": str(prefix),
            "executables": {"primary": str(primary), "native": str(primary)},
            "smoke_test": {"passed": True},
        }
    path = stack / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class ManagedDarwinStackTests(unittest.TestCase):
    def test_conda_create_uses_named_specs_only(self) -> None:
        source = (ROOT / "scripts/install_managed_hep_stack_macos.sh").read_text(
            encoding="utf-8"
        )
        create_start = source.index("run_logged runtime-create.log isolated_conda create")
        create_end = source.index("run_logged root-package-validation.log", create_start)
        transaction = source[create_start:create_end]
        self.assertIn('"${ROOT_MATCH}"', transaction)
        self.assertIn("python=3.11", transaction)
        self.assertNotIn('"${DOWNLOADS}/${ROOT_ARCHIVE}"', transaction)
        self.assertNotIn(".conda", transaction)

    def test_exact_root_match_specs_for_both_darwin_architectures(self) -> None:
        source = (ROOT / "scripts/install_managed_hep_stack_macos.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("ROOT_MATCH=root_base=6.40.02=cxx20_h17fc236_2", source)
        self.assertIn("ROOT_MATCH=root_base=6.40.02=cxx23_h36fdf7c_2", source)
        self.assertEqual(
            ROOT_PACKAGE_PLANS["arm64"].match_spec,
            "root_base=6.40.02=cxx20_h17fc236_2",
        )
        self.assertEqual(
            ROOT_PACKAGE_PLANS["x86_64"].match_spec,
            "root_base=6.40.02=cxx23_h36fdf7c_2",
        )

    def test_installed_root_metadata_build_and_checksum_validation(self) -> None:
        for architecture, plan in ROOT_PACKAGE_PLANS.items():
            with self.subTest(architecture=architecture), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                runtime = root / "runtime"
                downloads = root / "downloads"
                cache = root / "cache"
                (runtime / "conda-meta").mkdir(parents=True)
                downloads.mkdir()
                cache.mkdir()
                archive = downloads / plan.archive
                archive.write_bytes(b"verified root fixture")
                checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
                (cache / plan.archive).write_bytes(archive.read_bytes())
                replacement = type(plan)(
                    architecture=plan.architecture,
                    version=plan.version,
                    build=plan.build,
                    archive=plan.archive,
                    sha256=checksum,
                    subdir=plan.subdir,
                )
                metadata = {
                    "name": "root_base",
                    "version": plan.version,
                    "build": plan.build,
                    "subdir": plan.subdir,
                    "fn": plan.archive,
                }
                if architecture == "arm64":
                    metadata["sha256"] = checksum
                (runtime / "conda-meta" / f"root_base-{plan.version}-{plan.build}.json").write_text(
                    json.dumps(metadata), encoding="utf-8"
                )
                with patch.dict(ROOT_PACKAGE_PLANS, {architecture: replacement}):
                    result = validate_root_package(
                        architecture=architecture,
                        runtime_root=runtime,
                        downloads=downloads,
                        package_cache=cache,
                    )
                self.assertEqual(result["build"], plan.build)
                self.assertEqual(result["sha256"], checksum)

    def test_root_checksum_mismatch_fails_closed(self) -> None:
        plan = ROOT_PACKAGE_PLANS["arm64"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / "runtime"
            downloads = root / "downloads"
            (runtime / "conda-meta").mkdir(parents=True)
            downloads.mkdir()
            (downloads / plan.archive).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                validate_root_package(
                    architecture="arm64",
                    runtime_root=runtime,
                    downloads=downloads,
                    package_cache=root / "cache",
                )

    def test_interrupted_owned_install_recovers_and_preserves_downloads(self) -> None:
        ownership = ROOT / "scripts/managed_stack_ownership.sh"
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary).resolve() / "clone"
            repository.mkdir()
            stack = repository / ".hep-stack"
            command = f'''set -Eeuo pipefail
source "{ownership}"
initialize_managed_stack_ownership "{repository}" "{stack}"
mkdir -p "{stack}/downloads" "{stack}/runtime/bin" "{stack}/build"
printf verified >"{stack}/downloads/archive.tgz"
recover_incomplete_managed_stack "{repository}" "{stack}"
test -f "{stack}/downloads/archive.tgz"
test ! -e "{stack}/runtime"
test ! -e "{stack}/build"
test -f "{stack}/.installer-ownership"
'''
            completed = subprocess.run(
                ["bash", "-c", command], capture_output=True, text=True, check=False
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("downloads were preserved", completed.stdout)

    def test_recovery_refuses_outside_or_unowned_stack(self) -> None:
        ownership = ROOT / "scripts/managed_stack_ownership.sh"
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary).resolve() / "clone"
            repository.mkdir()
            outside = Path(temporary).resolve() / "outside"
            outside.mkdir()
            boundary = subprocess.run(
                [
                    "bash",
                    "-c",
                    f'source "{ownership}"; recover_incomplete_managed_stack "{repository}" "{outside}"',
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(boundary.returncode, 0)
            self.assertIn("outside the current clone", boundary.stderr)

            unowned = repository / ".hep-stack"
            unowned.mkdir()
            (unowned / "runtime").mkdir()
            ownership_result = subprocess.run(
                [
                    "bash",
                    "-c",
                    f'source "{ownership}"; recover_incomplete_managed_stack "{repository}" "{unowned}"',
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(ownership_result.returncode, 0)
            self.assertIn("unowned or ambiguous", ownership_result.stderr)

    def test_failure_report_names_stage_status_log_and_retry(self) -> None:
        source = (ROOT / "scripts/install_managed_hep_stack_macos.sh").read_text(
            encoding="utf-8"
        )
        for message in (
            "Failed stage: ${CURRENT_STAGE}",
            "Exit status: ${status}",
            "Relevant log: ${CURRENT_LOG}",
            "Verified downloads preserved: yes",
            "Safe retry: cd",
        ):
            self.assertIn(message, source)

    def test_root_smoke_ends_with_success_expression(self) -> None:
        source = (ROOT / "scripts/finalize_managed_stack.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "std::cout << gROOT->GetVersion() << std::endl; 0;",
            source,
        )

    def test_apple_clang_marker_is_written_only_after_linkage_audit(self) -> None:
        source = (ROOT / "scripts/finalize_managed_stack.py").read_text(
            encoding="utf-8"
        )
        audit = source.index("for name, target in linkage_targets().items()")
        marker = source.index('native_marker = STACK_ROOT / "pythia8/.heptoolbench-apple-clang"')
        launchers = source.index("launcher_records =", audit)
        self.assertLess(audit, marker)
        self.assertLess(marker, launchers)
        self.assertIn("linkage audit passed", source[marker:launchers])

    def test_conda_transaction_discards_external_hep_and_conda_environment(self) -> None:
        source = (ROOT / "scripts/install_managed_hep_stack_macos.sh").read_text(
            encoding="utf-8"
        )
        start = source.index("isolated_conda()")
        end = source.index("stage \"[1/8]", start)
        function = source[start:end]
        self.assertIn("env -i", function)
        self.assertIn('PATH="${MINIFORGE_ROOT}/bin:/usr/bin:/bin:/usr/sbin:/sbin"', function)
        self.assertIn("CONDA_SOLVER=libmamba", function)
        for variable in ("ROOTSYS", "PYTHIA8DATA", "DYLD_LIBRARY_PATH", "PYTHONPATH", "VIRTUAL_ENV"):
            self.assertNotIn(variable, function)

    def test_independent_bootstrap_has_both_pinned_darwin_plans(self) -> None:
        script = ROOT / "scripts/bootstrap_independent_hep_agent.sh"
        cases = {
            "arm64": (
                "Miniforge3-26.3.2-2-MacOSX-arm64.sh",
                "root_base-6.40.02-cxx20_h17fc236_2.conda",
            ),
            "x86_64": (
                "Miniforge3-26.3.2-2-MacOSX-x86_64.sh",
                "root_base-6.40.02-cxx23_h36fdf7c_2.conda",
            ),
        }
        for architecture, expected in cases.items():
            with self.subTest(architecture=architecture):
                environment = {
                    "PATH": "/usr/bin:/bin",
                    "HOME": "/tmp/fake-home",
                    "HEP_AGENT_TEST_PLATFORM": "Darwin",
                    "HEP_AGENT_TEST_ARCH": architecture,
                    "ROOTSYS": "/opt/root",
                    "CONDA_PREFIX": "/Users/test/miniforge3",
                    "DYLD_LIBRARY_PATH": "/opt/homebrew/lib",
                }
                completed = subprocess.run(
                    ["bash", str(script), "--dry-run", "--yes"],
                    capture_output=True,
                    text=True,
                    check=False,
                    env=environment,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn(f"Platform: Darwin {architecture}", completed.stdout)
                self.assertIn(expected[0], completed.stdout)
                self.assertIn(expected[1], completed.stdout)
                self.assertIn(".hep-stack/miniforge", completed.stdout)
                self.assertIn(".hep-stack/runtime", completed.stdout)
                self.assertNotIn("/opt/root", completed.stdout)
                self.assertNotIn("/opt/homebrew", completed.stdout)
                self.assertNotIn("/Users/test/miniforge3", completed.stdout)

    def test_macos_builder_is_clone_owned_and_has_no_external_discovery(self) -> None:
        source = (ROOT / "scripts/install_managed_hep_stack_macos.sh").read_text(
            encoding="utf-8"
        )
        for required in (
            'MINIFORGE_ROOT="${STACK_ROOT}/miniforge"',
            'RUNTIME_ROOT="${STACK_ROOT}/runtime"',
            'CONDA_PACKAGES="${STACK_ROOT}/conda-pkgs"',
            "env -i",
            "--override-channels -c conda-forge",
            "CC=/usr/bin/clang",
            "CXX=/usr/bin/clang++",
            "unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS",
            "export AR=/usr/bin/ar",
            "-D_LIBCPP_DISABLE_AVAILABILITY",
            "Pythia example link-order stanza was not found exactly once",
            "-lpythia8 -ldl $(GZIP_LIB)",
            '--with-hepmc2="${STACK_ROOT}/hepmc2"',
            "--with-gzip",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "brew --prefix",
            "/opt/homebrew",
            "/usr/local",
            "command -v root",
            "command -v root-config",
            "~/.local/share/hep-agent-tools",
            '--with-gzip="${RUNTIME_ROOT}"',
        ):
            self.assertNotIn(forbidden, source)

    def test_darwin_runtime_environment_replaces_all_poison(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "clone"
            stack = repository / ".hep-stack"
            libraries = (
                stack / "pythia8/lib",
                stack / "runtime/lib",
                stack / "hepmc2/lib",
            )
            poison = {
                "PATH": "/snap/bin:/opt/homebrew/bin:/opt/root/bin",
                "ROOTSYS": "/opt/root",
                "PYTHIA8DATA": "/old/xml",
                "LD_LIBRARY_PATH": "/old/linux",
                "DYLD_LIBRARY_PATH": "/old/macos",
                "PYTHONPATH": "/old/clone/.venv",
                "VIRTUAL_ENV": "/old/clone/.venv",
                "CONDA_PREFIX": "/old/conda",
                "CONDA_DEFAULT_ENV": "base",
                "CONDA_SHLVL": "3",
                "CMAKE_PREFIX_PATH": "/opt/homebrew",
                "ROOT_INCLUDE_PATH": "/opt/root/include",
                "LIBRARY_PATH": "/external/lib",
                "CPATH": "/external/include",
                "PKG_CONFIG_PATH": "/external/pkgconfig",
            }
            with (
                patch("hep_agent.runtime.stack.platform.system", return_value="Darwin"),
                patch(
                    "hep_agent.runtime.stack._darwin_sdk_root",
                    return_value=stack / "runtime/SDKs/MacOSX.sdk",
                ),
            ):
                environment = build_controlled_environment(
                    repository_root=repository,
                    stack_root=stack,
                    python_prefix=repository / ".venv",
                    root_prefix=stack / "runtime",
                    pythia8_data=stack / "pythia8/share/Pythia8/xmldoc",
                    library_paths=libraries,
                    executable_directories=(stack / "madgraph/bin",),
                    inherited=poison,
                )
            self.assertEqual(environment["ROOTSYS"], str(stack / "runtime"))
            self.assertEqual(
                environment["DYLD_LIBRARY_PATH"],
                os.pathsep.join(str(path) for path in libraries),
            )
            self.assertNotIn("LD_LIBRARY_PATH", environment)
            self.assertNotIn("CONDA_PREFIX", environment)
            joined = "\n".join(environment.values())
            for external in ("/opt/root", "/opt/homebrew", "/old/conda", "/old/clone", "/snap"):
                self.assertNotIn(external, joined)

    def test_otool_rpath_resolution_accepts_owned_and_rejects_external_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stack = Path(temporary) / "clone/.hep-stack"
            target = stack / "delphes/DelphesHepMC2"
            target.parent.mkdir(parents=True)
            target.touch()
            managed_root = stack / "runtime/lib"
            managed_root.mkdir(parents=True)
            (managed_root / "libCore.6.40.so").touch()
            load_commands = (
                "Load command 1\n"
                "          cmd LC_RPATH\n"
                "      cmdsize 88\n"
                f"         path {managed_root} (offset 12)\n"
            )
            libraries = (
                f"{target}:\n"
                "\t@rpath/libCore.6.40.so (compatibility version 6.40.0, current version 6.40.2)\n"
                "\t/usr/lib/libc++.1.dylib (compatibility version 1.0.0, current version 1.0.0)\n"
            )
            report = validate_macho_linkage(
                target, stack, libraries, load_commands
            )
            self.assertTrue(report["passed"], report)
            self.assertEqual(
                report["resolved_paths"],
                [str((managed_root / "libCore.6.40.so").resolve())],
            )

            external = libraries.replace(
                "@rpath/libCore.6.40.so",
                "/opt/homebrew/opt/root/lib/libCore.6.40.so",
            )
            report = validate_macho_linkage(target, stack, external, load_commands)
            self.assertFalse(report["passed"])
            self.assertIn("outside stack", "\n".join(report["failures"]))

    def test_pythia_must_use_apple_system_libcpp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stack = Path(temporary) / ".hep-stack"
            target = stack / "pythia8/lib/libpythia8.dylib"
            target.parent.mkdir(parents=True)
            target.touch()
            output = (
                f"{target}:\n"
                "\t@rpath/libpythia8.dylib "
                "(compatibility version 0.0.0, current version 0.0.0)\n"
                f"\t{stack}/runtime/lib/libc++.1.dylib "
                "(compatibility version 1.0.0, current version 1.0.0)\n"
            )
            report = validate_macho_linkage(
                target,
                stack,
                output,
                "",
                enforce_system_libcpp=True,
            )
            self.assertFalse(report["passed"])
            self.assertIn("operating-system libc++", "\n".join(report["failures"]))

            system = output.replace(
                f"{stack}/runtime/lib/libc++.1.dylib",
                "/usr/lib/libc++.1.dylib",
            )
            report = validate_macho_linkage(
                target,
                stack,
                system,
                "",
                enforce_system_libcpp=True,
            )
            self.assertTrue(report["passed"], report)
            self.assertNotIn("@rpath/libpythia8.dylib", report["resolved_paths"])

    def test_otool_relative_library_resolves_from_target_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stack = Path(temporary) / "clone/.hep-stack"
            target = stack / "madanalysis5/tools/SampleAnalyzer/Bin/TestRoot"
            library = stack / "madanalysis5/tools/SampleAnalyzer/Lib/libroot_for_ma5.so"
            target.parent.mkdir(parents=True)
            library.parent.mkdir(parents=True)
            target.touch()
            library.touch()
            output = (
                f"{target}:\n"
                "\t../Lib/libroot_for_ma5.so "
                "(compatibility version 0.0.0, current version 0.0.0)\n"
                "\t/usr/lib/libc++.1.dylib "
                "(compatibility version 1.0.0, current version 1.0.0)\n"
            )
            report = validate_macho_linkage(target, stack, output, "")
            self.assertTrue(report["passed"], report)
            self.assertEqual(report["resolved_paths"], [str(library.resolve())])

    def test_darwin_manifest_requires_clone_miniforge_and_pinned_root(self) -> None:
        for architecture in ("arm64", "x86_64"):
            with self.subTest(architecture=architecture), tempfile.TemporaryDirectory() as temporary:
                repository = Path(temporary) / "clone"
                path = darwin_manifest(repository, architecture)
                fake_python = repository / ".venv/bin/python"
                with (
                    patch("hep_agent.runtime.stack.platform.system", return_value="Darwin"),
                    patch("hep_agent.runtime.stack.platform.machine", return_value=architecture),
                    patch("hep_agent.runtime.stack.sys.executable", str(fake_python)),
                ):
                    manifest = load_stack_manifest(
                        path, expected_repository_root=repository
                    )
                self.assertEqual(manifest.root_prefix, repository / ".hep-stack/runtime")

                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["python"]["runtime_provider"]["manager_prefix"] = "/Users/test/miniforge3"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with (
                    patch("hep_agent.runtime.stack.platform.system", return_value="Darwin"),
                    patch("hep_agent.runtime.stack.platform.machine", return_value=architecture),
                    patch("hep_agent.runtime.stack.sys.executable", str(fake_python)),
                    self.assertRaisesRegex(StackConfigurationError, "Miniforge prefix"),
                ):
                    load_stack_manifest(path, expected_repository_root=repository)


if __name__ == "__main__":
    unittest.main()
