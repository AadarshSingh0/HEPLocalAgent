"""Tests for persistent web-interface history helpers."""

import json
import tempfile
import unittest
from pathlib import Path

from hep_agent.ui.web_support import (
    archive_run_history,
    load_run_history,
    read_text_tail,
    resolve_record_path,
)


class WebSupportTests(unittest.TestCase):
    def test_history_is_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            for run_id in (
                "20260101T000000_a",
                "20260102T000000_b",
            ):
                payload = {
                    "run_id": run_id,
                    "user_request": run_id,
                }

                (
                    root / f"{run_id}.json"
                ).write_text(
                    json.dumps(payload),
                    encoding="utf-8",
                )

            history = load_run_history(root)

            self.assertEqual(
                history[0].run_id,
                "20260102T000000_b",
            )

    def test_invalid_json_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            (root / "bad.json").write_text(
                "{not valid",
                encoding="utf-8",
            )

            self.assertEqual(
                load_run_history(root),
                (),
            )

    def test_history_limit_is_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            for index in range(5):
                path = root / f"{index}.json"
                path.write_text(
                    json.dumps(
                        {"run_id": str(index)}
                    ),
                    encoding="utf-8",
                )

            self.assertEqual(
                len(
                    load_run_history(
                        root,
                        limit=2,
                    )
                ),
                2,
            )

    def test_relative_record_path_is_resolved(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = resolve_record_path(
                root,
                "results/example.txt",
            )

            self.assertEqual(
                result,
                (
                    root
                    / "results"
                    / "example.txt"
                ).resolve(),
            )

    def test_absolute_record_path_is_preserved(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            absolute = (
                Path(temporary)
                / "example.txt"
            ).resolve()

            result = resolve_record_path(
                "/unused",
                absolute,
            )

            self.assertEqual(
                result,
                absolute,
            )

    def test_text_tail_returns_requested_lines(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = (
                Path(temporary)
                / "log.txt"
            )

            path.write_text(
                "\n".join(
                    f"line-{index}"
                    for index in range(10)
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                read_text_tail(
                    path,
                    max_lines=3,
                ),
                "line-7\nline-8\nline-9",
            )


    def test_run_history_is_archived_not_deleted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = root / "records"
            archives = root / "archives"

            records.mkdir()

            for run_id in (
                "run_a",
                "run_b",
            ):
                (
                    records / f"{run_id}.json"
                ).write_text(
                    json.dumps(
                        {
                            "run_id": run_id,
                        }
                    ),
                    encoding="utf-8",
                )

            archive_directory, count = (
                archive_run_history(
                    records,
                    archives,
                )
            )

            self.assertEqual(
                count,
                2,
            )

            self.assertIsNotNone(
                archive_directory
            )

            assert archive_directory is not None

            self.assertEqual(
                tuple(
                    records.glob("*.json")
                ),
                (),
            )

            self.assertTrue(
                (
                    archive_directory
                    / "run_a.json"
                ).is_file()
            )

            self.assertTrue(
                (
                    archive_directory
                    / "run_b.json"
                ).is_file()
            )

    def test_archiving_empty_history_is_noop(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            archive_directory, count = (
                archive_run_history(
                    root / "missing",
                    root / "archives",
                )
            )

            self.assertIsNone(
                archive_directory
            )

            self.assertEqual(
                count,
                0,
            )

if __name__ == "__main__":
    unittest.main()
