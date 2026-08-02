"""Data models for HEP-agent environment diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class CheckStatus(str, Enum):
    """Outcome of one doctor check."""

    PASS = "pass"
    WARNING = "warning"
    FAILURE = "failure"


@dataclass(frozen=True)
class DoctorCheck:
    """One environment or installation check."""

    check_id: str
    label: str
    status: CheckStatus
    summary: str
    required: bool = True
    details: dict[str, Any] | None = None
    remediation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True)
class DoctorReport:
    """Complete doctor result."""

    generated_at_utc: str
    project_root: str
    selected_profile: str
    deep_checks: bool
    checks: tuple[DoctorCheck, ...]

    @classmethod
    def create(
        cls,
        *,
        project_root: Path,
        selected_profile: str,
        deep_checks: bool,
        checks: list[DoctorCheck],
    ) -> "DoctorReport":
        return cls(
            generated_at_utc=datetime.now(
                timezone.utc
            ).isoformat(),
            project_root=str(project_root),
            selected_profile=selected_profile,
            deep_checks=deep_checks,
            checks=tuple(checks),
        )

    @property
    def failures(self) -> tuple[DoctorCheck, ...]:
        return tuple(
            check
            for check in self.checks
            if check.status is CheckStatus.FAILURE
        )

    @property
    def warnings(self) -> tuple[DoctorCheck, ...]:
        return tuple(
            check
            for check in self.checks
            if check.status is CheckStatus.WARNING
        )

    @property
    def passes(self) -> tuple[DoctorCheck, ...]:
        return tuple(
            check
            for check in self.checks
            if check.status is CheckStatus.PASS
        )

    @property
    def healthy(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at_utc": self.generated_at_utc,
            "project_root": self.project_root,
            "selected_profile": self.selected_profile,
            "deep_checks": self.deep_checks,
            "healthy": self.healthy,
            "summary": {
                "passed": len(self.passes),
                "warnings": len(self.warnings),
                "failures": len(self.failures),
                "total": len(self.checks),
            },
            "checks": [
                check.to_dict()
                for check in self.checks
            ],
        }
