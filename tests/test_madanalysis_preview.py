"""Tests for deterministic MA5 command previews."""

import unittest

from hep_agent.analysis import (
    compile_madanalysis_plan_commands,
    compile_madanalysis_quicklook_commands,
)

from test_madanalysis_builder import (
    make_dilepton_workflow,
)
from test_structured_madanalysis import (
    make_structured_plan,
)


class MadAnalysisPreviewTests(
    unittest.TestCase
):
    def test_quicklook_preview_has_expected_plots(
        self,
    ) -> None:
        commands = (
            compile_madanalysis_quicklook_commands(
                make_dilepton_workflow()
            )
        )

        self.assertEqual(
            len(commands),
            6,
        )
        self.assertIn(
            "plot PT(e+[1]) 40 0 400",
            commands,
        )
        self.assertIn(
            "plot M(e+ e-) 50 0 500",
            commands,
        )
        self.assertIn(
            "plot MET 40 0 400",
            commands,
        )

    def test_structured_preview_is_exact(
        self,
    ) -> None:
        commands = (
            compile_madanalysis_plan_commands(
                make_dilepton_workflow(),
                make_structured_plan(),
            )
        )

        self.assertEqual(
            commands,
            (
                "select PT(e+[1]) > 20",
                "select ABSETA(e+[1]) < 2.5",
                (
                    "plot M(e+[1] e-[1]) "
                    "30 60 120"
                ),
                "plot PT(e+[1]) 40 0 200",
            ),
        )


if __name__ == "__main__":
    unittest.main()
