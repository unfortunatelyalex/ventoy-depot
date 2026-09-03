import hashlib
from pathlib import Path

from ventoy_depot.iso import identify_iso, read_iso_volume_id, verify_detected_iso
from ventoy_depot.models import DetectedIso, IsoIdentity, ReleaseArtifact


def iso_with_volume_id(path: Path, volume_id: str) -> None:
    prefix = b"\0" * (16 * 2048)
    descriptor = bytearray(2048)
    descriptor[0] = 1
    descriptor[1:6] = b"CD001"
    descriptor[6] = 1
    descriptor[40:72] = volume_id.encode("ascii").ljust(32, b" ")
    path.write_bytes(prefix + descriptor)


def test_primary_volume_identifier_is_read_without_mounting(tmp_path: Path) -> None:
    path = tmp_path / "renamed.iso"
    iso_with_volume_id(path, "Ubuntu 26.04.1 LTS amd64")

    assert read_iso_volume_id(path) == "Ubuntu 26.04.1 LTS amd64"


def test_unknown_filename_retains_iso_volume_hint(tmp_path: Path) -> None:
    path = tmp_path / "renamed.iso"
    iso_with_volume_id(path, "GParted-live")

    detected = identify_iso(path)

    assert detected.identity is None
    assert detected.detection_source == "iso9660-volume-id"
    assert detected.confidence == 0.25
    assert detected.volume_id == "GParted-live"


def test_invalid_or_symlinked_image_has_no_volume_identifier(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.iso"
    invalid.write_bytes(b"not an ISO")
    symlink = tmp_path / "linked.iso"
    symlink.symlink_to(invalid)

    assert read_iso_volume_id(invalid) is None
    assert read_iso_volume_id(symlink) is None


def test_current_local_iso_is_compared_with_official_release_checksum(tmp_path: Path) -> None:
    path = tmp_path / "current.iso"
    path.write_bytes(b"verified")
    identity = IsoIdentity("test", "test", None, None, "stable", "amd64", None, "2", None)
    target = ReleaseArtifact(
        "2",
        None,
        path.name,
        "https://example.test/current.iso",
        path.stat().st_size,
        "sha512",
        hashlib.sha512(b"verified").hexdigest(),
        None,
        (),
        frozenset({"example.test"}),
        identity,
    )

    result = verify_detected_iso(DetectedIso(path, identity, 1.0, "test"), target)

    assert result.algorithm == "sha512"
    assert result.verified is True
    assert result.expected == target.checksum


def test_older_local_iso_is_hashed_without_comparing_to_latest_checksum(
    tmp_path: Path,
) -> None:
    path = tmp_path / "old.iso"
    path.write_bytes(b"old")
    installed = IsoIdentity("test", "test", None, None, "stable", "amd64", None, "1", None)
    latest = ReleaseArtifact(
        "2",
        None,
        "new.iso",
        "https://example.test/new.iso",
        3,
        "sha256",
        "0" * 64,
        None,
        (),
        frozenset({"example.test"}),
        IsoIdentity("test", "test", None, None, "stable", "amd64", None, "2", None),
    )

    result = verify_detected_iso(DetectedIso(path, installed, 1.0, "test"), latest)

    assert result.algorithm == "sha256"
    assert result.expected is None
    assert result.verified is None
