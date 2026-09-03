from __future__ import annotations

import hashlib
from pathlib import Path

from .models import DetectedIso
from .providers import Provider, provider_map


def identify_iso(path: Path, providers: tuple[Provider, ...] | None = None) -> DetectedIso:
    matches: list[DetectedIso] = []
    active = providers or tuple(provider_map().values())
    for provider in active:
        if detected := provider.detect(path):
            matches.append(detected)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return DetectedIso(path, None, 0.0, "ambiguous")
    return DetectedIso(path, None, 0.0, "unknown")


def find_isos(mount_path: Path, providers: tuple[Provider, ...] | None = None) -> list[DetectedIso]:
    root = mount_path.resolve(strict=True)
    active = providers or tuple(provider_map().values())
    entries: list[DetectedIso] = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".iso":
            continue
        try:
            path.resolve(strict=True).relative_to(root)
        except ValueError:
            continue
        entries.append(identify_iso(path, active))
    return sorted(entries, key=lambda entry: str(entry.path).lower())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
