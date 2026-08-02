"""Tests for web-interface HEP tool health detection."""

import tempfile
import unittest
from pathlib import Path

from hep_agent.ui.web_support import (
    detect_hep_tool_status,
)


def make_executable(path: Path) -> Path:
    """Create one synthetic executable."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        "#!/bin/sh\nexit 0\n",
        encoding="utf-8",
    )
    path.chmod(0o755)

    return path


class WebToolStatusTests(unittest.TestCase):
    def test_complete_mg5_toolchain_is_detected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mg5_root = root / "MG5_aMC"

            mg5 = make_executable(
                mg5_root / "bin" / "mg5_aMC"
            )
            make_executable(
                mg5_root
                / "HEPTools"
                / "pythia8"
                / "bin"
                / "pythia8-config"
            )
            make_executable(
                mg5_root
                / "Delphes"
                / "DelphesHepMC3"
            )
            (
                mg5_root
                / "Delphes"
                / "cards"
            ).mkdir(
                parents=True,
                exist_ok=True,
            )

            ma5 = make_executable(
                root / "madanalysis5" / "bin" / "ma5"
            )

            statuses = detect_hep_tool_status(
                {
                    "mg5_executable": str(mg5),
                    "madanalysis5_executable": str(ma5),
                }
            )

            availability = {
                status.key: status.available
                for status in statuses
            }

            self.assertEqual(
                availability,
                {
                    "madgraph": True,
                    "pythia8": True,
                    "delphes": True,
                    "madanalysis5": True,
                },
            )

    def test_missing_pythia_is_reported(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mg5 = make_executable(
                root
                / "MG5_aMC"
                / "bin"
                / "mg5_aMC"
            )

            statuses = detect_hep_tool_status(
                {"mg5_executable": str(mg5)}
            )

            pythia = next(
                status
                for status in statuses
                if status.key == "pythia8"
            )

            self.assertFalse(
                pythia.available
            )

    def test_delphes_requires_executable_and_cards(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mg5_root = root / "MG5_aMC"
            mg5 = make_executable(
                mg5_root / "bin" / "mg5_aMC"
            )

            make_executable(
                mg5_root
                / "Delphes"
                / "DelphesHepMC3"
            )

            statuses = detect_hep_tool_status(
                {"mg5_executable": str(mg5)}
            )

            delphes = next(
                status
                for status in statuses
                if status.key == "delphes"
            )

            self.assertFalse(
                delphes.available
            )

    def test_explicit_paths_are_supported(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            pythia = make_executable(
                root
                / "custom_pythia"
                / "bin"
                / "pythia8-config"
            )

            delphes_root = (
                root / "custom_delphes"
            )
            make_executable(
                delphes_root
                / "DelphesHepMC"
            )
            (
                delphes_root / "cards"
            ).mkdir(
                parents=True,
                exist_ok=True,
            )

            statuses = detect_hep_tool_status(
                {
                    "pythia8_executable": str(
                        pythia
                    ),
                    "delphes_path": str(
                        delphes_root
                    ),
                }
            )

            availability = {
                status.key: status.available
                for status in statuses
            }

            self.assertTrue(
                availability["pythia8"]
            )
            self.assertTrue(
                availability["delphes"]
            )


if __name__ == "__main__":
    unittest.main()
