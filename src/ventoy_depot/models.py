from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class UpdateAction(StrEnum):
    ADD = "add"
    REPLACE = "replace"
    SKIP = "skip"


class VerificationLevel(StrEnum):
    SIGNED = "signed"
    CHECKSUM = "checksum"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class IsoIdentity:
    provider_id: str
    product_id: str
    edition: str | None
    flavor: str | None
    channel: str
    architecture: str
    language: str | None
    version: str | None
    build: str | None

    def variant_key(self) -> tuple[str, str, str | None, str | None, str, str, str | None]:
        return (
            self.provider_id,
            self.product_id,
            self.edition,
            self.flavor,
            self.channel,
            self.architecture,
            self.language,
        )


@dataclass(frozen=True)
class ReleaseArtifact:
    version: str
    build: str | None
    filename: str
    download_url: str
    size_bytes: int | None
    checksum_algorithm: str
    checksum: str
    signature_url: str | None
    signer_fingerprints: tuple[str, ...]
    allowed_hosts: frozenset[str]

    @property
    def verification_level(self) -> VerificationLevel:
        if self.signature_url and self.signer_fingerprints:
            return VerificationLevel.SIGNED
        if self.checksum_algorithm in {"sha256", "sha512"} and self.checksum:
            return VerificationLevel.CHECKSUM
        return VerificationLevel.UNVERIFIED


@dataclass(frozen=True)
class Device:
    identifier: str
    display_name: str
    mount_path: Path
    size_bytes: int | None
    free_bytes: int | None
    is_removable: bool
    is_ventoy: bool
    detection_reason: str = ""


@dataclass(frozen=True)
class DetectedIso:
    path: Path
    identity: IsoIdentity | None
    confidence: float
    detection_source: str
    sha256: str | None = None


@dataclass(frozen=True)
class PlanItem:
    local: DetectedIso
    target: ReleaseArtifact | None
    action: UpdateAction
    free_bytes: int | None
    required_bytes: int | None
    verification_level: VerificationLevel
    warnings: tuple[str, ...] = ()
    blocking_errors: tuple[str, ...] = ()

    @property
    def writable(self) -> bool:
        return not self.blocking_errors and self.action != UpdateAction.SKIP


@dataclass(frozen=True)
class UpdatePlan:
    device: Device
    items: tuple[PlanItem, ...]
    plan_id: str

    @property
    def required_bytes(self) -> int:
        return sum(item.required_bytes or 0 for item in self.items if item.writable)


def to_jsonable(value: Any) -> Any:
    """Convert public immutable models to stable JSON-compatible values."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, frozenset, tuple, list)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value


def is_newer_version(candidate: str, installed: str | None) -> bool:
    if installed is None:
        return True
    try:
        from packaging.version import Version
    except ImportError:
        return _numeric_key(candidate) > _numeric_key(installed)
    try:
        return Version(candidate) > Version(installed)
    except ValueError:
        return _numeric_key(candidate) > _numeric_key(installed)


def _numeric_key(value: str) -> tuple[tuple[int, int | str], ...]:
    import re

    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in re.findall(r"\d+|[A-Za-z]+", value)
    )
