"""Non-visual support functions for the local Streamlit interface."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunHistoryEntry:
    """One persistent JSON run record available to the web UI."""

    path: Path
    payload: dict[str, Any]

    @property
    def run_id(self) -> str:
        return str(
            self.payload.get(
                "run_id",
                self.path.stem,
            )
        )

    @property
    def status(self) -> str:
        return str(
            self.payload.get("final_status")
            or self.payload.get("preexecution_status")
            or "prepared"
        )

    @property
    def request(self) -> str:
        return str(
            self.payload.get("user_request")
            or "Request unavailable"
        )

    @property
    def label(self) -> str:
        preview = " ".join(
            self.request.split()
        )

        if len(preview) > 54:
            preview = preview[:51] + "..."

        return (
            f"{self.run_id} · "
            f"{self.status} · "
            f"{preview}"
        )


def load_run_history(
    records_directory: str | Path,
    *,
    limit: int = 100,
) -> tuple[RunHistoryEntry, ...]:
    """Load the newest valid run-record JSON files."""

    if limit < 1:
        raise ValueError("limit must be at least one.")

    directory = (
        Path(records_directory)
        .expanduser()
        .resolve()
    )

    if not directory.is_dir():
        return ()

    entries: list[RunHistoryEntry] = []

    for path in sorted(
        directory.glob("*.json"),
        reverse=True,
    ):
        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            continue

        if not isinstance(payload, dict):
            continue

        entries.append(
            RunHistoryEntry(
                path=path,
                payload=payload,
            )
        )

        if len(entries) >= limit:
            break

    return tuple(entries)




def archive_run_history(
    records_directory: str | Path,
    archive_root: str | Path,
) -> tuple[Path | None, int]:
    """Move persistent run-record JSON files into an archive.

    Scientific outputs, execution directories, analyses, and scan
    results are intentionally left untouched.

    If moving any record fails, previously moved records are restored.
    """

    source_directory = (
        Path(records_directory)
        .expanduser()
        .resolve()
    )

    if not source_directory.is_dir():
        return None, 0

    record_paths = tuple(
        sorted(
            source_directory.glob("*.json")
        )
    )

    if not record_paths:
        return None, 0

    archive_directory = (
        Path(archive_root)
        .expanduser()
        .resolve()
        / datetime.now(
            timezone.utc
        ).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
    )

    archive_directory.mkdir(
        parents=True,
        exist_ok=False,
    )

    moved_paths: list[
        tuple[Path, Path]
    ] = []

    try:
        for source_path in record_paths:
            destination_path = (
                archive_directory
                / source_path.name
            )

            shutil.move(
                str(source_path),
                str(destination_path),
            )

            moved_paths.append(
                (
                    source_path,
                    destination_path,
                )
            )

    except Exception:
        for (
            source_path,
            destination_path,
        ) in reversed(moved_paths):
            if destination_path.exists():
                shutil.move(
                    str(destination_path),
                    str(source_path),
                )

        try:
            archive_directory.rmdir()
        except OSError:
            pass

        raise

    return (
        archive_directory,
        len(moved_paths),
    )


def resolve_record_path(
    project_root: str | Path,
    value: str | Path | None,
) -> Path | None:
    """Resolve a portable run-record path."""

    if value is None:
        return None

    raw = str(value).strip()

    if not raw:
        return None

    path = Path(raw).expanduser()

    if path.is_absolute():
        return path.resolve()

    return (
        Path(project_root)
        .expanduser()
        .resolve()
        / path
    ).resolve()


def read_text_tail(
    path: str | Path | None,
    *,
    max_lines: int = 120,
) -> str:
    """Read the final lines of one text file."""

    if path is None:
        return ""

    if max_lines < 1:
        raise ValueError(
            "max_lines must be at least one."
        )

    file_path = Path(path)

    if not file_path.is_file():
        return ""

    text = file_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    lines = text.splitlines()

    return "\n".join(lines[-max_lines:])


@dataclass(frozen=True)
class HepToolStatus:
    """Availability information for one external HEP tool."""

    key: str
    label: str
    available: bool
    path: Path | None
    detail: str


def _resolved_optional_path(
    value: str | Path | None,
) -> Path | None:
    """Resolve one optional local filesystem path."""

    if value is None:
        return None

    raw = str(value).strip()

    if not raw:
        return None

    return Path(raw).expanduser().resolve()


def _first_existing_path(
    candidates: tuple[Path | None, ...],
) -> Path | None:
    """Return the first existing candidate path."""

    for candidate in candidates:
        if candidate is not None and candidate.exists():
            return candidate

    return None


def _is_executable_file(path: Path | None) -> bool:
    """Whether a path is an executable regular file."""

    return bool(
        path is not None
        and path.is_file()
        and os.access(path, os.X_OK)
    )


def detect_hep_tool_status(
    local_paths: dict[str, Any],
) -> tuple[HepToolStatus, ...]:
    """Inspect availability of the configured HEP toolchain.

    Pythia8 and Delphes may either be explicitly configured or located
    inside the MadGraph installation.
    """

    mg5_executable = _resolved_optional_path(
        local_paths.get("mg5_executable")
    )

    mg5_root: Path | None = None

    if mg5_executable is not None:
        # Expected layout:
        #   <MG5 root>/bin/mg5_aMC
        mg5_root = mg5_executable.parent.parent

    ma5_executable = _resolved_optional_path(
        local_paths.get(
            "madanalysis5_executable"
        )
    )

    explicit_pythia_executable = _resolved_optional_path(
        local_paths.get(
            "pythia8_executable"
        )
    )

    explicit_pythia_directory = _resolved_optional_path(
        local_paths.get("pythia8_path")
        or local_paths.get(
            "pythia8_directory"
        )
    )

    inferred_pythia_directory = (
        mg5_root / "HEPTools" / "pythia8"
        if mg5_root is not None
        else None
    )

    pythia_directory = _first_existing_path(
        (
            explicit_pythia_directory,
            inferred_pythia_directory,
        )
    )

    inferred_pythia_executable = (
        pythia_directory
        / "bin"
        / "pythia8-config"
        if pythia_directory is not None
        else None
    )

    pythia_executable = _first_existing_path(
        (
            explicit_pythia_executable,
            inferred_pythia_executable,
        )
    )

    pythia_library_found = bool(
        pythia_directory is not None
        and pythia_directory.is_dir()
        and (
            list(
                pythia_directory.glob(
                    "lib/libpythia8.*"
                )
            )
            or list(
                pythia_directory.glob(
                    "lib64/libpythia8.*"
                )
            )
        )
    )

    pythia_available = (
        _is_executable_file(
            pythia_executable
        )
        or pythia_library_found
    )

    explicit_delphes_directory = _resolved_optional_path(
        local_paths.get("delphes_path")
        or local_paths.get(
            "delphes_directory"
        )
    )

    inferred_delphes_directory = (
        mg5_root / "Delphes"
        if mg5_root is not None
        else None
    )

    delphes_directory = _first_existing_path(
        (
            explicit_delphes_directory,
            inferred_delphes_directory,
        )
    )

    delphes_executables: tuple[Path, ...] = ()

    if delphes_directory is not None:
        delphes_executables = (
            delphes_directory / "DelphesHepMC3",
            delphes_directory / "DelphesHepMC",
            delphes_directory / "DelphesSTDHEP",
        )

    delphes_executable = _first_existing_path(
        tuple(
            executable
            for executable in delphes_executables
            if _is_executable_file(executable)
        )
    )

    delphes_cards_found = bool(
        delphes_directory is not None
        and (
            delphes_directory / "cards"
        ).is_dir()
    )

    delphes_available = bool(
        delphes_executable is not None
        and delphes_cards_found
    )

    return (
        HepToolStatus(
            key="madgraph",
            label="MadGraph",
            available=_is_executable_file(
                mg5_executable
            ),
            path=mg5_executable,
            detail=(
                "Deterministic event-generation backend."
            ),
        ),
        HepToolStatus(
            key="pythia8",
            label="Pythia8",
            available=pythia_available,
            path=(
                pythia_executable
                or pythia_directory
            ),
            detail=(
                "Showering and hadronization through "
                "the MadGraph installation."
            ),
        ),
        HepToolStatus(
            key="delphes",
            label="Delphes",
            available=delphes_available,
            path=(
                delphes_executable
                or delphes_directory
            ),
            detail=(
                "Fast detector simulation with "
                "installed detector cards."
            ),
        ),
        HepToolStatus(
            key="madanalysis5",
            label="MadAnalysis 5",
            available=_is_executable_file(
                ma5_executable
            ),
            path=ma5_executable,
            detail=(
                "Separate deterministic analysis "
                "and report-generation stage."
            ),
        ),
    )


def should_disable_request_input(
    *,
    prepared_exists: bool,
    prepared_is_ready: bool,
    final_result_exists: bool,
) -> bool:
    """Whether the chat input must wait for an approval decision.

    Only a successfully prepared workflow awaiting approval should
    block new input. Failed or blocked preparations must not trap the
    user on the page.
    """

    return (
        prepared_exists
        and prepared_is_ready
        and not final_result_exists
    )


def approval_countdown_seconds(
    *,
    deadline_timestamp: float,
    current_timestamp: float,
) -> int:
    """Return whole seconds remaining before automatic approval."""

    import math

    return max(
        0,
        math.ceil(
            deadline_timestamp
            - current_timestamp
        ),
    )


def failure_validation_issues(
    result: Any,
) -> list[dict[str, Any]]:
    """Collect real grounding and artifact errors for failure display."""

    issues: list[dict[str, Any]] = []

    for stage, report in (
        ("grounding", result.grounding_report),
        ("artifact", result.artifact_report),
    ):
        if report is None:
            continue

        issues.extend(
            {
                "stage": stage,
                "code": issue.code,
                "message": issue.message,
                "path": issue.path,
            }
            for issue in report.errors
        )

    return issues
