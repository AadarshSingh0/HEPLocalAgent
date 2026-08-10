"""Tests for validated external-execution outcomes."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from hep_agent.execution.outcome import (
    DETECTOR_ROOT_OUTPUT,
    PARTON_LEVEL_LHE_OUTPUT,
    SHOWERED_HEPMC_OUTPUT,
    execution_has_valid_physics_output,
    validate_execution_outputs,
)


class ExecutionOutcomeTests(
    unittest.TestCase
):
    @staticmethod
    def _physics(
        root: Path,
        *,
        lhe: bool = True,
        hepmc: bool = False,
        detector: bool = False,
        has_summary: bool = True,
    ) -> SimpleNamespace:
        paths: dict[str, Path | None] = {
            "primary_lhe_file": None,
            "showered_hepmc_file": None,
            "detector_root_file": None,
        }

        requested = {
            "primary_lhe_file": (
                "unweighted_events.lhe.gz",
                lhe,
            ),
            "showered_hepmc_file": (
                "events.hepmc.gz",
                hepmc,
            ),
            "detector_root_file": (
                "events.root",
                detector,
            ),
        }

        for field, (name, present) in requested.items():
            if present:
                path = root / name
                path.write_bytes(b"output")
                paths[field] = path

        return SimpleNamespace(
            has_physics_summary=has_summary,
            **paths,
        )

    def test_subprocess_failure_is_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            physics = self._physics(Path(temporary))

            self.assertFalse(
                execution_has_valid_physics_output(
                    SimpleNamespace(success=False),
                    physics,
                )
            )

    def test_missing_parser_result_is_failure(
        self,
    ) -> None:
        execution = SimpleNamespace(
            success=True
        )

        validation = validate_execution_outputs(
            execution,
            None,
        )

        self.assertFalse(validation.is_valid)
        self.assertEqual(
            validation.missing_requested_outputs,
            (PARTON_LEVEL_LHE_OUTPUT,),
        )

    def test_missing_physics_summary_is_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            physics = self._physics(
                Path(temporary),
                has_summary=False,
            )

            self.assertFalse(
                execution_has_valid_physics_output(
                    SimpleNamespace(success=True),
                    physics,
                )
            )

    def test_missing_lhe_is_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            physics = self._physics(
                Path(temporary),
                lhe=False,
            )

            validation = validate_execution_outputs(
                SimpleNamespace(success=True),
                physics,
            )

        self.assertFalse(validation.is_valid)
        self.assertEqual(
            validation.missing_requested_outputs,
            (PARTON_LEVEL_LHE_OUTPUT,),
        )

    def test_unrequested_later_outputs_are_optional(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            physics = self._physics(Path(temporary))

            self.assertTrue(
                execution_has_valid_physics_output(
                    SimpleNamespace(success=True),
                    physics,
                )
            )

    def test_requested_hepmc_is_required(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            physics = self._physics(Path(temporary))

            validation = validate_execution_outputs(
                SimpleNamespace(success=True),
                physics,
                require_hepmc=True,
            )

        self.assertFalse(validation.is_valid)
        self.assertEqual(
            validation.missing_requested_outputs,
            (SHOWERED_HEPMC_OUTPUT,),
        )

    def test_requested_root_is_required(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            physics = self._physics(
                Path(temporary),
                hepmc=True,
            )

            validation = validate_execution_outputs(
                SimpleNamespace(success=True),
                physics,
                require_hepmc=True,
                require_root=True,
            )

        self.assertFalse(validation.is_valid)
        self.assertEqual(
            validation.missing_requested_outputs,
            (DETECTOR_ROOT_OUTPUT,),
        )

    def test_all_missing_requested_outputs_are_reported(
        self,
    ) -> None:
        validation = validate_execution_outputs(
            SimpleNamespace(success=True),
            None,
            require_hepmc=True,
            require_root=True,
        )

        self.assertFalse(validation.is_valid)
        self.assertEqual(
            validation.missing_requested_outputs,
            (
                PARTON_LEVEL_LHE_OUTPUT,
                SHOWERED_HEPMC_OUTPUT,
                DETECTOR_ROOT_OUTPUT,
            ),
        )

    def test_all_requested_outputs_are_success(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            physics = self._physics(
                Path(temporary),
                hepmc=True,
                detector=True,
            )

            validation = validate_execution_outputs(
                SimpleNamespace(success=True),
                physics,
                require_hepmc=True,
                require_root=True,
            )

        self.assertTrue(validation.is_valid)
        self.assertEqual(
            validation.missing_requested_outputs,
            (),
        )


if __name__ == "__main__":
    unittest.main()
