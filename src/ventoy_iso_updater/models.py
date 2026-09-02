from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Distro(StrEnum):
    ARCH = "arch"
    DEBIAN = "debian"
    FEDORA = "fedora"
    MINT = "mint"
    UBUNTU = "ubuntu"
    UNKNOWN = "unknown"


class UpdateAction(StrEnum):
    ADD = "add"
    REPLACE = "replace"
    SKIP = "skip"


@dataclass(frozen=True)
class Device:
    identifier: str
    display_name: str
    mount_path: Path
    size_bytes: int | None
    is_removable: bool
    is_ventoy: bool


@dataclass(frozen=True)
class IsoEntry:
    path: Path
    distro: Distro
    version: str | None
    architecture: str | None


@dataclass(frozen=True)
class Release:
    distro: Distro
    version: str
    architecture: str
    download_url: str
    checksum_url: str
    checksum_filename: str
    signature_url: str | None = None
    checksum_algorithm: str = "sha256"


@dataclass(frozen=True)
class UpdatePlan:
    existing: IsoEntry
    release: Release
    action: UpdateAction


def is_newer_version(candidate: str, installed: str | None) -> bool:
    """Compare dotted numeric release versions without accepting a downgrade."""
    if installed is None or candidate == "latest":
        return True
    try:
        candidate_parts = tuple(int(part) for part in candidate.split("."))
        installed_parts = tuple(int(part) for part in installed.split("."))
    except ValueError:
        return candidate != installed
    width = max(len(candidate_parts), len(installed_parts))
    return candidate_parts + (0,) * (width - len(candidate_parts)) > installed_parts + (0,) * (
        width - len(installed_parts)
    )
