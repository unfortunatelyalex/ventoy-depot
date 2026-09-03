from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ventoy_depot.devices import DeviceError
from ventoy_depot.models import (
    DetectedIso,
    Device,
    IsoIdentity,
    PlanItem,
    ReleaseArtifact,
    UpdateAction,
    VerificationLevel,
)
from ventoy_depot.transfer import (
    TransferCancelled,
    TransferError,
    _download,
    _trash,
    _verify_openpgp,
    apply_item,
)


class Response:
    status = 200

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0
        self.closed = False
        self.headers = {"Content-Length": str(len(data)), "ETag": '"fixture"'}

    def read(self, amount: int = -1) -> bytes:
        if self.offset >= len(self.data):
            return b""
        end = len(self.data) if amount < 0 else self.offset + amount
        block = self.data[self.offset : end]
        self.offset += len(block)
        return block

    def close(self) -> None:
        self.closed = True


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
    assert not (tmp_path / "cache" / f"{destination.name}.download").exists()


def test_short_signer_fingerprint_is_rejected_before_gpg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ventoy_depot.transfer.shutil.which", lambda _name: "gpgv")
    artifact = tmp_path / "image.iso"
    signature = tmp_path / "image.iso.sig"
    keyring = tmp_path / "trusted.gpg"
    for path in (artifact, signature, keyring):
        path.touch()
    with pytest.raises(TransferError, match="fingerprint"):
        _verify_openpgp(artifact, signature, keyring, ("DEADBEEF",))


def test_label_detected_device_does_not_require_marker_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    Client.data = b"new verified ISO"
    monkeypatch.setattr("ventoy_depot.transfer.SafeHttpClient", Client)
    seen: list[Device] = []

    def revalidate(device: Device) -> Device:
        seen.append(device)
        return device

    monkeypatch.setattr("ventoy_depot.transfer.revalidate_device", revalidate)
    plan_item = item(tmp_path, hashlib.sha256(Client.data).hexdigest())
    device = Device(
        "/dev/sdb1",
        "/dev/sdb1 (Ventoy)",
        tmp_path,
        10**9,
        10**9,
        True,
        True,
        "volume-label",
    )

    destination = apply_item(plan_item, cache_dir=tmp_path / "cache", device=device)

    assert destination.read_bytes() == Client.data
    assert seen == [device, device, device]


def test_download_closes_response_when_size_is_exceeded(tmp_path: Path) -> None:
    response = Response(b"too large")

    class OneResponseClient:
        def open(self, _url: str, _headers: dict[str, str]) -> Response:
            return response

    with pytest.raises(TransferError, match="exceeded"):
        _download(OneResponseClient(), "https://example.org/image.iso", tmp_path / "image", 1, None)  # type: ignore[arg-type]
    assert response.closed


def test_complete_resumable_download_is_verified_without_network(tmp_path: Path) -> None:
    target = tmp_path / "image.download"
    target.write_bytes(b"complete")
    target.with_suffix(".download.json").write_text('{"validator": "etag"}\n', encoding="utf-8")

    class OfflineClient:
        def open(self, _url: str, _headers: dict[str, str]) -> Response:
            raise AssertionError("a complete cached download must not request a range past EOF")

    _download(OfflineClient(), "https://example.org/image.iso", target, len(b"complete"), None)  # type: ignore[arg-type]


def test_changed_resume_validator_closes_response_before_restart(tmp_path: Path) -> None:
    target = tmp_path / "image.download"
    target.write_bytes(b"old")
    target.with_suffix(".download.json").write_text('{"validator": "old-etag"}\n', encoding="utf-8")
    first = Response(b"ignored")
    first.status = 206
    first.headers["ETag"] = "new-etag"
    second = Response(b"fresh!")

    class SequenceClient:
        calls = 0

        def open(self, _url: str, _headers: dict[str, str]) -> Response:
            self.calls += 1
            if self.calls == 1:
                return first
            assert first.closed
            return second

    _download(  # type: ignore[arg-type]
        SequenceClient(), "https://example.org/image.iso", target, len(b"fresh!"), None
    )
    assert target.read_bytes() == b"fresh!"


def test_target_created_during_copy_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".ventoy").touch()
    Client.data = b"new verified ISO"
    monkeypatch.setattr("ventoy_depot.transfer.SafeHttpClient", Client)
    monkeypatch.setattr("ventoy_depot.transfer.revalidate_device", lambda device: device)
    plan_item = item(tmp_path, hashlib.sha256(Client.data).hexdigest())
    assert plan_item.target is not None
    destination = tmp_path / plan_item.target.filename

    def concurrent_copy(source: Path, partial: Path, _progress: object) -> None:
        partial.write_bytes(source.read_bytes())
        destination.write_bytes(b"created concurrently")

    monkeypatch.setattr("ventoy_depot.transfer._copy", concurrent_copy)
    with pytest.raises(TransferError, match="already exists"):
        apply_item(plan_item, cache_dir=tmp_path / "cache")
    assert destination.read_bytes() == b"created concurrently"
    assert plan_item.local.path.read_bytes() == b"old ISO"
    assert not destination.with_name(destination.name + ".partial").exists()


def test_changed_device_is_not_cleaned_or_finalized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    Client.data = b"new verified ISO"
    monkeypatch.setattr("ventoy_depot.transfer.SafeHttpClient", Client)
    plan_item = item(tmp_path, hashlib.sha256(Client.data).hexdigest())
    assert plan_item.target is not None
    destination = tmp_path / plan_item.target.filename
    device = Device("uuid", "Ventoy", tmp_path, 100, 100, True, True, "volume-label")
    checks = 0

    def changed_after_copy(current: Device) -> Device:
        nonlocal checks
        checks += 1
        if checks >= 3:
            raise DeviceError("device changed")
        return current

    monkeypatch.setattr("ventoy_depot.transfer.revalidate_device", changed_after_copy)
    with pytest.raises(DeviceError, match="changed"):
        apply_item(plan_item, cache_dir=tmp_path / "cache", device=device)
    assert not destination.exists()
    assert destination.with_name(destination.name + ".partial").exists()
    assert plan_item.local.path.read_bytes() == b"old ISO"


def test_cancellation_during_copy_removes_partial_and_preserves_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".ventoy").touch()
    Client.data = b"x" * (3 * 1024 * 1024)
    monkeypatch.setattr("ventoy_depot.transfer.SafeHttpClient", Client)
    monkeypatch.setattr("ventoy_depot.transfer.revalidate_device", lambda device: device)
    plan_item = item(tmp_path, hashlib.sha256(Client.data).hexdigest())
    assert plan_item.target is not None
    cancel = False

    def progress(stage: str, _completed: int, _total: int) -> None:
        nonlocal cancel
        if stage == "copy":
            cancel = True

    with pytest.raises(TransferCancelled):
        apply_item(
            plan_item,
            progress=progress,
            cache_dir=tmp_path / "cache",
            cancelled=lambda: cancel,
        )

    destination = tmp_path / plan_item.target.filename
    assert not destination.exists()
    assert not destination.with_name(destination.name + ".partial").exists()
    assert (tmp_path / "cache" / f"{destination.name}.download").exists()
    assert plan_item.local.path.read_bytes() == b"old ISO"


def test_unknown_download_size_is_bounded_by_staging_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = Response(b"12345")
    response.headers.pop("Content-Length")

    class OneResponseClient:
        def open(self, _url: str, _headers: dict[str, str]) -> Response:
            return response

    monkeypatch.setattr(
        "ventoy_depot.transfer.shutil.disk_usage",
        lambda _path: type("Usage", (), {"free": 4})(),
    )

    with pytest.raises(TransferError, match="staging directory"):
        _download(  # type: ignore[arg-type]
            OneResponseClient(), "https://example.org/image.iso", tmp_path / "image", None, None
        )

    assert response.closed


def test_trash_rejects_symlinked_metadata_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".ventoy-depot").symlink_to(outside, target_is_directory=True)
    iso = tmp_path / "old.iso"
    iso.write_bytes(b"old")

    with pytest.raises(Exception, match="[Ss]ymlink"):
        _trash(iso, tmp_path)

    assert iso.exists()
    assert not (outside / "trash" / iso.name).exists()
