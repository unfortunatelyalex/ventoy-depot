from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ventoy_depot.models import (
    DetectedIso,
    IsoIdentity,
    PlanItem,
    ReleaseArtifact,
    UpdateAction,
    VerificationLevel,
)
from ventoy_depot.transfer import TransferError, apply_item


class Response:
    status = 200

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0
        self.headers = {"Content-Length": str(len(data)), "ETag": '"fixture"'}

    def read(self, amount: int = -1) -> bytes:
        if self.offset >= len(self.data):
            return b""
        end = len(self.data) if amount < 0 else self.offset + amount
        block = self.data[self.offset : end]
        self.offset += len(block)
        return block

    def close(self) -> None:
        pass


class Client:
    data = b""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def open(self, _url: str, _headers: dict[str, str]) -> Response:
        return Response(self.data)


def item(root: Path, checksum: str) -> PlanItem:
    old = root / "archlinux-2025.03.01-x86_64.iso"
    old.write_bytes(b"old ISO")
    identity = IsoIdentity(
        "arch", "archlinux", None, None, "stable", "x86_64", None, "2025.03.01", None
    )
    artifact = ReleaseArtifact(
        "2026.09.01",
        None,
        "archlinux-2026.09.01-x86_64.iso",
        "https://example.org/arch.iso",
        len(Client.data),
        "sha256",
        checksum,
        None,
        (),
        frozenset({"example.org"}),
    )
    return PlanItem(
        DetectedIso(old, identity, 1.0, "fixture"),
        artifact,
        UpdateAction.ADD,
        10**9,
        len(Client.data),
        VerificationLevel.CHECKSUM,
    )


def test_verified_download_is_atomically_added_and_old_iso_remains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".ventoy").touch()
    Client.data = b"new verified ISO"
    monkeypatch.setattr("ventoy_depot.transfer.SafeHttpClient", Client)
    monkeypatch.setattr("ventoy_depot.transfer.revalidate_device", lambda device: device)
    plan_item = item(tmp_path, hashlib.sha256(Client.data).hexdigest())

    destination = apply_item(plan_item, cache_dir=tmp_path / "cache")

    assert destination.read_bytes() == Client.data
    assert plan_item.local.path.read_bytes() == b"old ISO"
    assert not destination.with_name(destination.name + ".partial").exists()


def test_bad_checksum_never_creates_visible_or_partial_iso(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".ventoy").touch()
    Client.data = b"tampered ISO"
    monkeypatch.setattr("ventoy_depot.transfer.SafeHttpClient", Client)
    monkeypatch.setattr("ventoy_depot.transfer.revalidate_device", lambda device: device)
    plan_item = item(tmp_path, "0" * 64)
    destination = tmp_path / plan_item.target.filename  # type: ignore[union-attr]

    with pytest.raises(TransferError, match="checksum"):
        apply_item(plan_item, cache_dir=tmp_path / "cache")

    assert not destination.exists()
    assert not destination.with_name(destination.name + ".partial").exists()
    assert plan_item.local.path.exists()
