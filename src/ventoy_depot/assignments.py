from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .iso import sha256_file
from .models import IsoIdentity


class AssignmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class Assignment:
    relative_path: str
    source_sha256: str
    identity: IsoIdentity


class AssignmentCatalog:
    """Hash-bound assignments for renamed or ambiguous ISOs on one Ventoy drive."""

    def __init__(self, mount_path: Path) -> None:
        self.mount_path = mount_path.resolve(strict=True)
        self.path = self.mount_path / ".ventoy-depot" / "catalog.json"

    def lookup(self, iso_path: Path) -> IsoIdentity | None:
        assignment = self._records().get(self._relative(iso_path))
        if assignment is None or assignment.source_sha256 != sha256_file(iso_path):
            return None
        return assignment.identity

    def assign(self, iso_path: Path, identity: IsoIdentity) -> None:
        relative = self._relative(iso_path)
        records = self._records()
        records[relative] = Assignment(relative, sha256_file(iso_path), identity)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": 1,
            "assignments": [
                {
                    "relative_path": record.relative_path,
                    "source_sha256": record.source_sha256,
                    "identity": asdict(record.identity),
                }
                for record in sorted(records.values(), key=lambda item: item.relative_path)
            ],
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="catalog.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(document, output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_name, self.path)
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise

    def _records(self) -> dict[str, Assignment]:
        if not self.path.exists():
            return {}
        try:
            payload: Any = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != 1:
                raise AssignmentError("Unsupported assignment catalog schema.")
            return {
                item["relative_path"]: Assignment(
                    item["relative_path"],
                    item["source_sha256"],
                    IsoIdentity(**item["identity"]),
                )
                for item in payload["assignments"]
            }
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise AssignmentError("Assignment catalog is invalid.") from error

    def _relative(self, path: Path) -> str:
        if path.is_symlink():
            raise AssignmentError("Symlink assignments are not allowed.")
        try:
            return path.resolve(strict=True).relative_to(self.mount_path).as_posix()
        except ValueError as error:
            raise AssignmentError("ISO is outside the Ventoy mountpoint.") from error
