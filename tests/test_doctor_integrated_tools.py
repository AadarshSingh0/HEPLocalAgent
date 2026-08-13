"""Doctor checks for integrated HEP-tool installations."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hep_agent.doctor.checks import (
    _check_integrated_tools,
    _delphes_installation_check,
    _mg5_deep_smoke,
)
from hep_agent.doctor.models import CheckStatus


class IntegratedToolDoctorTests(unittest.TestCase):
    def _make_executable(self, path: Path) -> None:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.write_text(
            "#!/usr/bin/env bash\nexit 0\n",
            encoding="utf-8",
        )
        path.chmod(
            path.stat().st_mode | 0o111
        )

    def test_deep_mg5_smoke_uses_its_temporary_working_directory(self) -> None:
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch(
            "hep_agent.doctor.checks.subprocess.run",
            return_value=completed,
        ) as run:
            _mg5_deep_smoke(Path("/managed/mg5_aMC"), timeout_seconds=30)

        working_directory = run.call_args.kwargs["cwd"]
        self.assertIsInstance(working_directory, Path)
        self.assertTrue(working_directory.name.startswith("hep_agent_doctor_mg5_"))
        self.assertNotEqual(working_directory, Path.cwd())

    def test_directories_without_executables_warn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            mg5_root = Path(temporary) / "MG5"
            mg5 = mg5_root / "bin" / "mg5_aMC"
            self._make_executable(mg5)

            (
                mg5_root
                / "HEPTools"
                / "pythia8"
            ).mkdir(parents=True)

            (
                mg5_root
                / "Delphes"
            ).mkdir(parents=True)

            with mock.patch(
                "hep_agent.doctor.checks.platform.system",
                return_value="Linux",
            ):
                checks = _check_integrated_tools(
                    mg5,
                    {},
                )

            statuses = {
                check.check_id: check.status
                for check in checks
            }

            self.assertEqual(
                statuses["pythia8_installation"],
                CheckStatus.WARNING,
            )
            self.assertEqual(
                statuses["delphes_installation"],
                CheckStatus.WARNING,
            )

    def test_runnable_executables_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            mg5_root = Path(temporary) / "MG5"
            mg5 = mg5_root / "bin" / "mg5_aMC"
            self._make_executable(mg5)

            self._make_executable(
                mg5_root
                / "HEPTools"
                / "pythia8"
                / "bin"
                / "pythia8-config"
            )

            self._make_executable(
                mg5_root
                / "Delphes"
                / "DelphesHepMC2"
            )

            # This is the platform-neutral runnable-files case. Dedicated
            # tests below exercise Apple-Silicon's native-build marker.
            with mock.patch(
                "hep_agent.doctor.checks.platform.system",
                return_value="Linux",
            ):
                checks = _check_integrated_tools(
                    mg5,
                    {},
                )

            statuses = {
                check.check_id: check.status
                for check in checks
            }

            self.assertEqual(
                statuses["pythia8_installation"],
                CheckStatus.PASS,
            )
            self.assertEqual(
                statuses["delphes_installation"],
                CheckStatus.PASS,
            )

    def test_linux_delphes_undefined_root_symbol_warns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = (
                Path(temporary)
                / "DelphesHepMC2"
            )
            executable.write_bytes(b"\x7fELF")
            executable.chmod(
                executable.stat().st_mode | 0o111
            )
            linker_result = mock.Mock(
                returncode=1,
                stdout=(
                    "undefined symbol: "
                    "_ZNK3TF111GradientParEiPKdd\n"
                ),
                stderr="",
            )

            with (
                mock.patch(
                    "hep_agent.doctor.checks.platform.system",
                    return_value="Linux",
                ),
                mock.patch(
                    "hep_agent.doctor.checks.subprocess.run",
                    return_value=linker_result,
                ),
            ):
                check = _delphes_installation_check(
                    executable,
                    [executable],
                )

            self.assertEqual(
                check.status,
                CheckStatus.WARNING,
            )
            self.assertIn(
                "ROOT runtime linkage is not usable",
                check.summary,
            )
            self.assertIn(
                "undefined symbol",
                check.details["runtime_problem"],
            )

    def test_old_apple_silicon_pythia_warns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            mg5_root = Path(temporary) / "MG5"
            mg5 = mg5_root / "bin" / "mg5_aMC"
            self._make_executable(mg5)

            self._make_executable(
                mg5_root
                / "HEPTools"
                / "pythia8"
                / "bin"
                / "pythia8-config"
            )

            with (
                mock.patch(
                    "hep_agent.doctor.checks.platform.system",
                    return_value="Darwin",
                ),
                mock.patch(
                    "hep_agent.doctor.checks.platform.machine",
                    return_value="arm64",
                ),
            ):
                checks = _check_integrated_tools(
                    mg5,
                    {},
                )

            pythia = next(
                check
                for check in checks
                if check.check_id
                == "pythia8_installation"
            )
            self.assertEqual(
                pythia.status,
                CheckStatus.WARNING,
            )
            self.assertIn(
                "native-runtime repair",
                pythia.summary,
            )

    def test_repaired_apple_silicon_pythia_passes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            mg5_root = Path(temporary) / "MG5"
            mg5 = mg5_root / "bin" / "mg5_aMC"
            self._make_executable(mg5)

            pythia_prefix = (
                mg5_root
                / "HEPTools"
                / "pythia8"
            )
            self._make_executable(
                pythia_prefix
                / "bin"
                / "pythia8-config"
            )
            (
                pythia_prefix
                / ".heptoolbench-apple-clang"
            ).write_text(
                "native Apple Clang build\n",
                encoding="utf-8",
            )

            with (
                mock.patch(
                    "hep_agent.doctor.checks.platform.system",
                    return_value="Darwin",
                ),
                mock.patch(
                    "hep_agent.doctor.checks.platform.machine",
                    return_value="arm64",
                ),
            ):
                checks = _check_integrated_tools(
                    mg5,
                    {},
                )

            pythia = next(
                check
                for check in checks
                if check.check_id
                == "pythia8_installation"
            )
            self.assertEqual(
                pythia.status,
                CheckStatus.PASS,
            )


if __name__ == "__main__":
    unittest.main()
