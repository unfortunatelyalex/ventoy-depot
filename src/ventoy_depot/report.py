from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path


class ResultStatus(StrEnum):
    SUCCESS = "success"
    CURRENT = "current"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class ItemResult:
    path: str
    status: ResultStatus
    message: str


@dataclass(frozen=True)
class RunReport:
    plan_id: str
    results: tuple[ItemResult, ...]

    @property
    def successful(self) -> bool:
        return bool(self.results) and all(
            result.status in {ResultStatus.SUCCESS, ResultStatus.CURRENT} for result in self.results
        )

    def write(self, path: Path) -> None:
        document = json.dumps(
            {
                "schema_version": 1,
                "plan_id": self.plan_id,
                "successful": self.successful,
                "results": [asdict(result) for result in self.results],
            },
            ensure_ascii=False,
            indent=2,
        )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="report.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write(document + "\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_name, path)
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise
