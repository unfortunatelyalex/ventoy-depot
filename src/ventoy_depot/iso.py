from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from .models import DetectedIso, LocalVerification, ReleaseArtifact
from .providers import Provider, provider_map


def identify_iso(path: Path, providers: tuple[Provider, ...] | None = None) -> DetectedIso:
    matches: list[DetectedIso] = []
    active = providers or tuple(provider_map().values())
    for provider in active:
        if detected := provider.detect(path):
            matches.append(detected)
    volume_id = read_iso_volume_id(path)
    if len(matches) == 1:
        return replace(matches[0], volume_id=volume_id)
    if len(matches) > 1:
        return DetectedIso(path, None, 0.0, "ambiguous", volume_id=volume_id)
    if volume_id:
        return DetectedIso(path, None, 0.25, "iso9660-volume-id", volume_id=volume_id)
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
    return hash_file(path, "sha256")


def hash_file(path: Path, algorithm: str) -> str:
    if algorithm not in {"sha256", "sha512"}:
        raise ValueError("Only SHA-256 and SHA-512 are supported.")
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_detected_iso(detected: DetectedIso, target: ReleaseArtifact | None) -> LocalVerification:
    if detected.path.is_symlink() or not detected.path.is_file():
        raise OSError(f"ISO file not found or unsafe: {detected.path}")
    identity = detected.identity
    matches_target = bool(
        target
        and identity
        and identity.version == target.version
        and (target.build is None or identity.build == target.build)
    )
    algorithm = target.checksum_algorithm if matches_target and target else "sha256"
    checksum = hash_file(detected.path, algorithm)
    expected = target.checksum if matches_target and target else None
    return LocalVerification(
        detected.path,
        algorithm,
        checksum,
        expected,
        checksum.lower() == expected.lower() if expected else None,
    )


def read_iso_volume_id(path: Path) -> str | None:
    """Read the ISO-9660 primary volume identifier without mounting the image."""
    if path.is_symlink():
        return None
    try:
        with path.open("rb") as source:
            for sector in range(16, 32):
                source.seek(sector * 2048)
                descriptor = source.read(2048)
                if len(descriptor) != 2048:
                    return None
                if descriptor[1:6] != b"CD001" or descriptor[6] != 1:
                    continue
                if descriptor[0] == 255:
                    return None
                if descriptor[0] != 1:
                    continue
                volume_id = descriptor[40:72].decode("ascii", errors="replace").strip(" \0")
                return volume_id or None
    except OSError:
        return None
    return None
