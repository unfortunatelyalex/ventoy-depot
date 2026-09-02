from __future__ import annotations

import json
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
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "plan_id": self.plan_id,
                    "successful": self.successful,
                    "results": [asdict(result) for result in self.results],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
