"""Static tests for beginner installation shell scripts."""

from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BootstrapScriptTests(unittest.TestCase):
    def test_shell_scripts_have_valid_syntax(self) -> None:
        scripts = (
            ROOT.parent / "install.sh",
            ROOT.parent / "run_agent.sh",
            ROOT.parent / "run_benchmark.sh",
            ROOT.parent / "uninstall.sh",
            ROOT / "install.sh",
            ROOT / "run_agent.sh",
            ROOT / "uninstall.sh",
            ROOT / "scripts" / "bootstrap_local_hep_agent.sh",
            ROOT / "scripts" / "uninstall_local_hep_agent.sh",
        )

        for script in scripts:
            self.assertTrue(script.is_file(), script)
            completed = subprocess.run(
                ["bash", "-n", str(script)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr,
            )

    def test_repository_installer_is_safe_for_empty_apple_bash_array(
        self,
    ) -> None:
        script = ROOT.parent / "install.sh"
        source = script.read_text(encoding="utf-8")

        self.assertIn(
            'local -a agent_command=(',
            source,
        )
        self.assertIn(
            '"${agent_command[@]}"',
            source,
        )
        self.assertNotIn(
            '"${ROOT}/local_hep_agent/install.sh" "${AGENT_ARGS[@]}"',
            source,
        )

    def test_bootstrap_help_is_available(self) -> None:
        script = (
            ROOT
            / "scripts"
            / "bootstrap_local_hep_agent.sh"
        )
        completed = subprocess.run(
            ["bash", str(script), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("HEP Agent beginner installer", completed.stdout)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--full", completed.stdout)
        self.assertIn("--ollama-host", completed.stdout)
        self.assertIn("--python", completed.stdout)
        self.assertIn("--validate-full-stack", completed.stdout)

    def test_uninstall_help_is_available(self) -> None:
        script = ROOT.parent / "uninstall.sh"
        completed = subprocess.run(
            ["bash", str(script), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("HEPToolBench uninstaller", completed.stdout)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--purge-results", completed.stdout)
        self.assertIn("--remove-model", completed.stdout)

    def test_uninstaller_removes_only_managed_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            repository = temporary / "HEPToolBench"
            agent = repository / "local_hep_agent"
            scripts = agent / "scripts"
            configs = agent / "configs"
            benchmark = repository / "local_llm_benchmark"
            home = temporary / "home"

            scripts.mkdir(parents=True)
            configs.mkdir()
            (benchmark / "results").mkdir(parents=True)
            (benchmark / "runs" / "test-run").mkdir(parents=True)

            shutil.copy2(
                ROOT.parent / "uninstall.sh",
                repository / "uninstall.sh",
            )
            shutil.copy2(
                ROOT / "uninstall.sh",
                agent / "uninstall.sh",
            )
            shutil.copy2(
                ROOT / "scripts" / "uninstall_local_hep_agent.sh",
                scripts / "uninstall_local_hep_agent.sh",
            )

            (agent / ".venv" / "bin").mkdir(parents=True)
            (agent / ".venv" / "installed.txt").write_text(
                "installed\n",
                encoding="utf-8",
            )
            tools = home / ".local" / "share" / "hep-agent-tools"
            tools.mkdir(parents=True)
            (tools / "MG5_aMC").mkdir()

            profiles = {
                "legacy_llama3": {"primary_model": "llama3:8b"},
                "starter_local": {
                    "primary_model": "qwen2.5-coder:7b"
                },
            }
            (configs / "agent_profiles.json").write_text(
                json.dumps(profiles, indent=2) + "\n",
                encoding="utf-8",
            )
            for filename in (
                "local_paths.json",
                "ollama_host",
                "conda_root",
            ):
                (configs / filename).write_text(
                    "generated\n",
                    encoding="utf-8",
                )

            (agent / "results").mkdir()
            (agent / "results" / "user-run.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            (
                benchmark / "runs" / "test-run" / "score.csv"
            ).write_text(
                "score\n",
                encoding="utf-8",
            )
            (
                benchmark / "results" / "all_runs_long.csv"
            ).write_text(
                "score\n",
                encoding="utf-8",
            )
            canonical_result = benchmark / "results" / "README.md"
            canonical_result.write_text(
                "tracked canonical results\n",
                encoding="utf-8",
            )

            environment = os.environ.copy()
            environment["HOME"] = str(home)

            completed = subprocess.run(
                ["bash", str(repository / "uninstall.sh"), "--yes"],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr,
            )
            self.assertFalse((agent / ".venv").exists())
            self.assertFalse(tools.exists())
            self.assertFalse((configs / "local_paths.json").exists())
            self.assertFalse((configs / "ollama_host").exists())
            self.assertFalse((configs / "conda_root").exists())
            remaining_profiles = json.loads(
                (configs / "agent_profiles.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("legacy_llama3", remaining_profiles)
            self.assertNotIn("starter_local", remaining_profiles)

            self.assertTrue((agent / "results").exists())
            self.assertTrue((benchmark / "runs").exists())
            self.assertTrue(
                (
                    benchmark / "results" / "all_runs_long.csv"
                ).exists()
            )

            completed = subprocess.run(
                [
                    "bash",
                    str(repository / "uninstall.sh"),
                    "--yes",
                    "--purge-results",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr,
            )
            self.assertFalse((agent / "results").exists())
            self.assertFalse((benchmark / "runs").exists())
            self.assertFalse(
                (
                    benchmark / "results" / "all_runs_long.csv"
                ).exists()
            )
            self.assertTrue(canonical_result.exists())

    def test_uninstaller_refuses_unmarked_custom_tools_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            repository = temporary / "HEPToolBench"
            agent = repository / "local_hep_agent"
            scripts = agent / "scripts"
            custom_tools = temporary / "shared-tools"

            scripts.mkdir(parents=True)
            custom_tools.mkdir()
            (custom_tools / "keep.txt").write_text(
                "not owned by HEPToolBench\n",
                encoding="utf-8",
            )

            shutil.copy2(
                ROOT.parent / "uninstall.sh",
                repository / "uninstall.sh",
            )
            shutil.copy2(
                ROOT / "uninstall.sh",
                agent / "uninstall.sh",
            )
            shutil.copy2(
                ROOT / "scripts" / "uninstall_local_hep_agent.sh",
                scripts / "uninstall_local_hep_agent.sh",
            )

            environment = os.environ.copy()
            environment["HOME"] = str(temporary / "home")
            completed = subprocess.run(
                [
                    "bash",
                    str(repository / "uninstall.sh"),
                    "--yes",
                    "--tools-root",
                    str(custom_tools),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn(
                ".heptoolbench-managed",
                completed.stderr,
            )
            self.assertTrue((custom_tools / "keep.txt").exists())

    def test_madgraph_download_has_verified_official_fallback(self) -> None:
        script = (
            ROOT
            / "scripts"
            / "bootstrap_local_hep_agent.sh"
        )
        source = script.read_text(encoding="utf-8")

        self.assertIn(
            "github.com/mg5amcnlo/mg5amcnlo/archive/refs/tags/",
            source,
        )
        self.assertIn(
            "MG5_GITHUB_SHA256="
            '"0c75437481cc7808b59b578bc454d2c7'
            'bc12721b8bd848a287f35503202fabe7"',
            source,
        )
        self.assertIn(
            "trying the official GitHub",
            source,
        )
        self.assertIn(
            'TOOLS_MARKER_NAME=".heptoolbench-managed"',
            source,
        )

    def test_mg5_tool_invocation_is_safe_for_apple_bash(self) -> None:
        script = (
            ROOT
            / "scripts"
            / "bootstrap_local_hep_agent.sh"
        )
        source = script.read_text(encoding="utf-8")

        self.assertIn(
            'local -a mg5_invocation=("${MG5_EXECUTABLE}")',
            source,
        )
        self.assertIn(
            'mg5_invocation+=("${command_file}")',
            source,
        )
        self.assertNotIn(
            'local -a mg5_arguments=()',
            source,
        )

    def test_macos_core_install_has_a_safe_dry_run(self) -> None:
        script = (
            ROOT
            / "scripts"
            / "bootstrap_local_hep_agent.sh"
        )
        environment = os.environ.copy()
        environment.update(
            {
                "HEP_AGENT_TEST_PLATFORM": "Darwin",
                "HEP_AGENT_TEST_ARCH": "x86_64",
                "HEP_AGENT_TEST_MACOS_VERSION": "13.7.8",
            }
        )
        completed = subprocess.run(
            [
                "bash",
                str(script),
                "--dry-run",
                "--yes",
                "--install-system-deps",
                "--ollama-host",
                "http://192.0.2.10:11434",
                "--tools-root",
                "/tmp/hep-agent-macos-dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertIn(
            "Platform: Darwin",
            completed.stdout,
        )
        self.assertIn(
            "Miniforge3-26.3.2-2-MacOSX-x86_64.sh",
            completed.stdout,
        )
        self.assertIn("conda create", completed.stdout)
        self.assertIn(
            "hep-agent-mg5",
            completed.stdout,
        )
        self.assertIn(
            "http://192.0.2.10:11434",
            completed.stdout,
        )

    def test_macos_hep_stack_uses_conda_root_and_integrated_tools(
        self,
    ) -> None:
        script = (
            ROOT
            / "scripts"
            / "bootstrap_local_hep_agent.sh"
        )
        environment = os.environ.copy()
        environment.update(
            {
                "HEP_AGENT_TEST_PLATFORM": "Darwin",
                "HEP_AGENT_TEST_ARCH": "x86_64",
                "HEP_AGENT_TEST_MACOS_VERSION": "13.7.8",
            }
        )
        completed = subprocess.run(
            [
                "bash",
                str(script),
                "--dry-run",
                "--yes",
                "--install-system-deps",
                "--with-pythia8",
                "--with-delphes",
                "--with-madanalysis5",
                "--tools-root",
                "/tmp/hep-agent-macos-hep-dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertIn(
            "conda-forge --strict-channel-priority root",
            completed.stdout,
        )
        self.assertIn(
            "Installing Pythia8 through MadGraph",
            completed.stdout,
        )
        self.assertIn(
            "Installing Delphes through MadGraph",
            completed.stdout,
        )
        self.assertIn(
            "Using the conda-forge libc++ compatibility flag "
            "for Delphes",
            completed.stdout,
        )
        source = script.read_text(encoding="utf-8")
        self.assertIn(
            "patch_macos_delphes_makefile",
            source,
        )
        self.assertIn(
            "CXXFLAGS += -D_LIBCPP_DISABLE_AVAILABILITY",
            source,
        )
        self.assertIn(
            "repair_macos_delphes_build",
            source,
        )
        self.assertIn(
            "Installing MadAnalysis5 through MadGraph",
            completed.stdout,
        )

    def test_apple_silicon_pythia_uses_one_native_clang_runtime(
        self,
    ) -> None:
        script = (
            ROOT
            / "scripts"
            / "bootstrap_local_hep_agent.sh"
        )
        environment = os.environ.copy()
        environment.update(
            {
                "HEP_AGENT_TEST_PLATFORM": "Darwin",
                "HEP_AGENT_TEST_ARCH": "arm64",
                "HEP_AGENT_TEST_MACOS_VERSION": "14.0",
            }
        )
        completed = subprocess.run(
            [
                "bash",
                str(script),
                "--dry-run",
                "--yes",
                "--install-system-deps",
                "--with-pythia8",
                "--tools-root",
                "/tmp/hep-agent-apple-silicon-pythia-dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertIn(
            "build static HepMC2 2.06.11 with /usr/bin/clang++",
            completed.stdout,
        )
        self.assertIn(
            "compile with CC=/usr/bin/clang and "
            "CXX=/usr/bin/clang++ without Conda compiler/linker flags",
            completed.stdout,
        )
        self.assertIn(
            "set hepmc_path = "
            "/tmp/hep-agent-apple-silicon-pythia-dry-run/"
            "MG5_aMC/HEPTools/hepmc2-native-2.06.11 "
            "and pythia8_path = "
            "/tmp/hep-agent-apple-silicon-pythia-dry-run/"
            "MG5_aMC/HEPTools/pythia8",
            completed.stdout,
        )
        self.assertNotIn(
            "strict-channel-priority hepmc2=2.06.11",
            completed.stdout,
        )

        source = script.read_text(encoding="utf-8")
        self.assertIn(
            'PYTHIA8_INSTALL_COMMAND+=" '
            '--with_hepmc=${MACOS_ARM64_HEPMC2_PREFIX}"',
            source,
        )
        self.assertIn(
            "MG5's bundled HepMC 2.06.09",
            source,
        )
        self.assertIn(
            "configure_mg5_pythia_paths",
            source,
        )
        self.assertIn(
            "verify_macos_arm64_native_pythia",
            source,
        )
        self.assertIn(
            ".heptoolbench-apple-clang",
            source,
        )
        self.assertIn(
            'candidate_root="${cmake_file%/CMakeLists.txt}"',
            source,
        )
        self.assertIn(
            '-d "${candidate_root}/HepMC"',
            source,
        )
        self.assertNotIn(
            'source_root="${build_root}/hepmc${HEPMC2_VERSION}"',
            source,
        )
        self.assertIn(
            'grep -Fq "${VENV_DIR}/lib/libc++"',
            source,
        )
        self.assertIn(
            '"/usr/lib/libc++.1.dylib"',
            source,
        )

    def test_intel_macos_keeps_integrated_hepmc2_path(
        self,
    ) -> None:
        script = (
            ROOT
            / "scripts"
            / "bootstrap_local_hep_agent.sh"
        )
        environment = os.environ.copy()
        environment.update(
            {
                "HEP_AGENT_TEST_PLATFORM": "Darwin",
                "HEP_AGENT_TEST_ARCH": "x86_64",
                "HEP_AGENT_TEST_MACOS_VERSION": "13.7.8",
            }
        )
        completed = subprocess.run(
            [
                "bash",
                str(script),
                "--dry-run",
                "--yes",
                "--install-system-deps",
                "--with-pythia8",
                "--tools-root",
                "/tmp/hep-agent-intel-pythia-dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertNotIn(
            "hepmc2=2.06.11",
            completed.stdout,
        )
        self.assertIn(
            "Installing Pythia8 through MadGraph",
            completed.stdout,
        )

    def test_linux_hep_stack_has_a_safe_dry_run(self) -> None:
        script = (
            ROOT
            / "scripts"
            / "bootstrap_local_hep_agent.sh"
        )
        environment = os.environ.copy()
        environment.update(
            {
                "HEP_AGENT_TEST_PLATFORM": "Linux",
                "HEP_AGENT_TEST_ARCH": "x86_64",
            }
        )
        completed = subprocess.run(
            [
                "bash",
                str(script),
                "--dry-run",
                "--yes",
                "--install-system-deps",
                "--with-pythia8",
                "--with-delphes",
                "--with-madanalysis5",
                "--validate-full-stack",
                "--python",
                sys.executable,
                "--tools-root",
                "/tmp/hep-agent-linux-hep-dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertIn("Platform: Linux x86_64", completed.stdout)
        self.assertIn("sudo apt-get install", completed.stdout)
        self.assertIn(
            "Installing Pythia8 through MadGraph",
            completed.stdout,
        )
        self.assertIn(
            "Installing Delphes through MadGraph",
            completed.stdout,
        )
        self.assertIn(
            "Installing MadAnalysis5 through MadGraph",
            completed.stdout,
        )
        self.assertIn(
            "generate 10 real events through MadGraph, Pythia8, "
            "DelphesHepMC2, and MadAnalysis5",
            completed.stdout,
        )

        source = script.read_text(encoding="utf-8")
        self.assertIn(
            "verify_linux_delphes_runtime",
            source,
        )
        self.assertIn(
            "LD_BIND_NOW=1 ldd -r",
            source,
        )
        self.assertIn(
            "repair_linux_delphes_build",
            source,
        )
        self.assertIn(
            '"LD_LIBRARY_PATH=${root_libdir}"',
            source,
        )

    def test_linux_installer_rejects_snap_root(self) -> None:
        script = (
            ROOT
            / "scripts"
            / "bootstrap_local_hep_agent.sh"
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            fake_bin = temporary / "fake-bin"
            fake_bin.mkdir()

            root_config = fake_bin / "root-config"
            root_config.write_text(
                "#!/usr/bin/env bash\n"
                "case \"${1:-}\" in\n"
                "  --prefix) printf '%s\\n' "
                "'/snap/root-framework/current/usr/local' ;;\n"
                "  --libdir) printf '%s\\n' "
                "'/snap/root-framework/current/usr/local/lib' ;;\n"
                "  --version) printf '%s\\n' '6.40.02' ;;\n"
                "  *) exit 1 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            root_config.chmod(0o755)

            rootcint = fake_bin / "rootcint"
            rootcint.write_text(
                "#!/usr/bin/env bash\nexit 0\n",
                encoding="utf-8",
            )
            rootcint.chmod(0o755)

            environment = os.environ.copy()
            environment.update(
                {
                    "HEP_AGENT_TEST_PLATFORM": "Linux",
                    "HEP_AGENT_TEST_ARCH": "x86_64",
                    "PATH": f"{fake_bin}:{environment['PATH']}",
                }
            )
            completed = subprocess.run(
                [
                    "bash",
                    str(script),
                    "--dry-run",
                    "--yes",
                    "--with-delphes",
                    "--python",
                    sys.executable,
                    "--tools-root",
                    str(temporary / "tools"),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertIn(
            "Ignoring unsupported Snap ROOT",
            completed.stdout,
        )
        self.assertIn(
            "installing a managed ROOT copy",
            completed.stdout,
        )
        self.assertNotIn(
            "ROOT 6.40.02 is available.",
            completed.stdout,
        )

    def test_old_macos_rejects_local_ollama_install(self) -> None:
        script = (
            ROOT
            / "scripts"
            / "bootstrap_local_hep_agent.sh"
        )
        environment = os.environ.copy()
        environment.update(
            {
                "HEP_AGENT_TEST_PLATFORM": "Darwin",
                "HEP_AGENT_TEST_ARCH": "arm64",
                "HEP_AGENT_TEST_MACOS_VERSION": "13.7.8",
            }
        )
        completed = subprocess.run(
            [
                "bash",
                str(script),
                "--dry-run",
                "--yes",
                "--install-ollama",
                "--python",
                sys.executable,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn(
            "Ollama requires macOS 14 or newer",
            completed.stdout,
        )

    def test_modern_macos_uses_current_ollama_cask(self) -> None:
        script = (
            ROOT
            / "scripts"
            / "bootstrap_local_hep_agent.sh"
        )
        environment = os.environ.copy()
        environment.update(
            {
                "HEP_AGENT_TEST_PLATFORM": "Darwin",
                "HEP_AGENT_TEST_ARCH": "arm64",
                "HEP_AGENT_TEST_MACOS_VERSION": "14.0",
            }
        )
        completed = subprocess.run(
            [
                "bash",
                str(script),
                "--dry-run",
                "--yes",
                "--install-system-deps",
                "--install-ollama",
                "--ollama-host",
                "http://localhost:11434",
                "--tools-root",
                "/tmp/hep-agent-modern-macos-dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertIn(
            "brew install --cask ollama-app",
            completed.stdout,
        )

    def test_intel_macos_rejects_local_ollama_install(self) -> None:
        script = (
            ROOT
            / "scripts"
            / "bootstrap_local_hep_agent.sh"
        )
        environment = os.environ.copy()
        environment.update(
            {
                "HEP_AGENT_TEST_PLATFORM": "Darwin",
                "HEP_AGENT_TEST_ARCH": "x86_64",
                "HEP_AGENT_TEST_MACOS_VERSION": "14.0",
            }
        )
        completed = subprocess.run(
            [
                "bash",
                str(script),
                "--dry-run",
                "--yes",
                "--install-ollama",
                "--python",
                sys.executable,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn(
            "Current Ollama for macOS requires Apple Silicon",
            completed.stdout,
        )

    def test_intel_macos_allows_remote_model_pull(self) -> None:
        script = (
            ROOT
            / "scripts"
            / "bootstrap_local_hep_agent.sh"
        )
        environment = os.environ.copy()
        environment.update(
            {
                "HEP_AGENT_TEST_PLATFORM": "Darwin",
                "HEP_AGENT_TEST_ARCH": "x86_64",
                "HEP_AGENT_TEST_MACOS_VERSION": "13.7.8",
            }
        )
        completed = subprocess.run(
            [
                "bash",
                str(script),
                "--dry-run",
                "--yes",
                "--pull-model",
                "--python",
                sys.executable,
                "--ollama-host",
                "http://192.0.2.10:11434",
                "--tools-root",
                "/tmp/hep-agent-intel-remote-dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertIn(
            "pull qwen2.5-coder:7b from "
            "http://192.0.2.10:11434",
            completed.stdout,
        )


if __name__ == "__main__":
    unittest.main()
