from __future__ import annotations

import re
from pathlib import Path

from .models import Distro, IsoEntry

_RULES: tuple[tuple[Distro, re.Pattern[str]], ...] = (
    (
        Distro.UBUNTU,
        re.compile(r"ubuntu-(?P<version>\d+\.\d+(?:\.\d+)?)-.*?(?P<arch>amd64|arm64)", re.I),
    ),
    (
        Distro.FEDORA,
        re.compile(r"fedora(?:-workstation)?-live-(?P<arch>x86_64|aarch64)-(?P<version>\d+)", re.I),
    ),
    (
        Distro.DEBIAN,
        re.compile(r"debian-(?P<version>\d+(?:\.\d+){0,2})-.*?(?P<arch>amd64|arm64)", re.I),
    ),
    (
        Distro.ARCH,
        re.compile(r"archlinux-(?P<version>\d{4}\.\d{2}\.\d{2})-(?P<arch>x86_64)", re.I),
    ),
    (
        Distro.MINT,
        re.compile(r"linuxmint-(?P<version>\d+(?:\.\d+){0,2})-.*?(?P<arch>64bit|amd64)", re.I),
    ),
)


def identify_iso(path: Path) -> IsoEntry:
    name = path.name
    for distro, pattern in _RULES:
        match = pattern.search(name)
        if match:
            architecture = match.group("arch").lower().replace("64bit", "amd64")
            return IsoEntry(path, distro, match.group("version"), architecture)
    return IsoEntry(path, Distro.UNKNOWN, None, None)


def find_isos(mount_path: Path) -> list[IsoEntry]:
    return sorted(
        (
            identify_iso(path)
            for path in mount_path.rglob("*")
            if path.is_file() and path.suffix.lower() == ".iso"
        ),
        key=lambda iso: str(iso.path).lower(),
    )
