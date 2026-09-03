from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from securesystemslib.signer import CryptoSigner
from tuf.api.metadata import Metadata, MetaFile, Root, Snapshot, TargetFile, Targets, Timestamp

from ventoy_depot.registry_client import _load_cached, _refresh_due, load_registry
from ventoy_depot.security import SecurityError


def test_missing_bootstrap_root_uses_bundled_fallback(tmp_path: Path) -> None:
    snapshot = load_registry(refresh=True, root=tmp_path / "missing-root.json")
    assert snapshot.origin == "bundled"
    assert snapshot.manifests == ()
    assert "trust root" in (snapshot.warning or "")


def test_registry_refresh_is_limited_to_once_per_day(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    for name in ("timestamp.json", "snapshot.json", "targets.json"):
        (metadata / name).write_text("{}", encoding="utf-8")
    (tmp_path / "state.json").write_text(
        json.dumps({"checked_at": datetime.now(UTC).isoformat()}), encoding="utf-8"
    )
    assert not _refresh_due(tmp_path)
    old = datetime.now(UTC) - timedelta(days=2)
    (tmp_path / "state.json").write_text(
        json.dumps({"checked_at": old.isoformat()}), encoding="utf-8"
    )
    assert _refresh_due(tmp_path)


def test_cached_manifest_is_rechecked_against_signed_target_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    import hashlib

    index = tmp_path / "targets" / "providers" / "index.json"
    target = tmp_path / "targets" / "providers" / "example.json"
    target.parent.mkdir(parents=True)
    index.write_text(json.dumps({"schema_version": 1, "providers": ["example"]}), encoding="utf-8")
    target.write_text('{"provider_id":"example"}', encoding="utf-8")

    class TargetInfo:
        def __init__(self, data: bytes) -> None:
            self.digest = hashlib.sha256(data).hexdigest()

        def verify_length_and_hashes(self, data: bytes) -> None:
            if hashlib.sha256(data).hexdigest() != self.digest:
                raise ValueError("hash mismatch")

    targets = {
        "providers/index.json": TargetInfo(index.read_bytes()),
        "providers/example.json": TargetInfo(target.read_bytes()),
    }

    class OfflineUpdater:
        def refresh(self) -> None:
            pass

        def get_targetinfo(self, name: str):
            return targets.get(name)

    monkeypatch.setattr(
        "ventoy_depot.registry_client._offline_updater",
        lambda *_args: OfflineUpdater(),
    )
    monkeypatch.setattr(
        "ventoy_depot.registry_client.load_and_validate_manifest",
        lambda path: {"provider_id": "example", "path": str(path)},
    )
    assert _load_cached(tmp_path, tmp_path / "root.json") == [
        {"provider_id": "example", "path": str(target)}
    ]
    target.write_text("tampered", encoding="utf-8")
    with pytest.raises(SecurityError, match="TUF verification"):
        _load_cached(tmp_path, tmp_path / "root.json")


def test_registry_refresh_is_due_when_signed_metadata_is_missing(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text(
        json.dumps({"checked_at": datetime.now(UTC).isoformat()}), encoding="utf-8"
    )
    assert _refresh_due(tmp_path)


def test_real_tuf_chain_verifies_cached_manifest_and_rejects_cotampering(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    metadata_dir = cache / "metadata"
    target_dir = cache / "targets" / "providers"
    metadata_dir.mkdir(parents=True)
    target_dir.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "provider_id": "example",
        "display_name": "Example",
        "homepage_url": "https://example.org/",
        "driver": "static-json",
        "allowed_hosts": ["example.org"],
        "capabilities": {
            "products": ["example"],
            "editions": [],
            "flavors": [],
            "architectures": ["x86_64"],
            "languages": [],
            "channels": ["stable"],
        },
        "release_sources": [
            {
                "source_id": "stable",
                "metadata_url": "https://example.org/releases.json",
                "artifact_regex": r"^example-(?P<version>[0-9.]+)\.iso$",
                "identity": {
                    "product_id": "example",
                    "channel": "stable",
                    "architecture": "x86_64",
                },
                "download": {
                    "strategy": "url-template",
                    "url_template": "https://example.org/{filename}",
                },
                "verification": {
                    "level": "CHECKSUM",
                    "checksum": {"algorithm": "sha256", "strategy": "embedded-json"},
                },
            }
        ],
        "detection": [
            {
                "regex": r"^example-(?P<version>[0-9.]+)\.iso$",
                "identity": {
                    "product_id": "example",
                    "channel": "stable",
                    "architecture": "x86_64",
                    "version": "$group:version",
                },
                "downloadable": True,
            }
        ],
    }
    index_path = target_dir / "index.json"
    manifest_path = target_dir / "example.json"
    index_path.write_text(json.dumps({"schema_version": 1, "providers": ["example"]}))
    manifest_path.write_text(json.dumps(manifest))
    expires = datetime.now(UTC) + timedelta(days=7)
    signers = {
        role: CryptoSigner.generate_ed25519()
        for role in ("root", "targets", "snapshot", "timestamp")
    }
    root = Metadata(Root(expires=expires, consistent_snapshot=False))
    for role, signer in signers.items():
        root.signed.add_key(signer.public_key, role)
    root.sign(signers["root"])
    trust_root = tmp_path / "root.json"
    root.to_file(str(trust_root))
    targets = Metadata(
        Targets(
            expires=expires,
            targets={
                "providers/index.json": TargetFile.from_file(
                    "providers/index.json", str(index_path), ["sha256"]
                ),
                "providers/example.json": TargetFile.from_file(
                    "providers/example.json", str(manifest_path), ["sha256"]
                ),
            },
        )
    )
    targets.sign(signers["targets"])
    targets_bytes = targets.to_bytes()
    (metadata_dir / "targets.json").write_bytes(targets_bytes)
    targets_meta = MetaFile(
        targets.signed.version,
        len(targets_bytes),
        {"sha256": hashlib.sha256(targets_bytes).hexdigest()},
    )
    snapshot = Metadata(Snapshot(expires=expires, meta={"targets.json": targets_meta}))
    snapshot.sign(signers["snapshot"])
    snapshot_bytes = snapshot.to_bytes()
    (metadata_dir / "snapshot.json").write_bytes(snapshot_bytes)
    snapshot_meta = MetaFile(
        snapshot.signed.version,
        len(snapshot_bytes),
        {"sha256": hashlib.sha256(snapshot_bytes).hexdigest()},
    )
    timestamp = Metadata(Timestamp(expires=expires, snapshot_meta=snapshot_meta))
    timestamp.sign(signers["timestamp"])
    (metadata_dir / "timestamp.json").write_bytes(timestamp.to_bytes())

    assert _load_cached(cache, trust_root)[0]["provider_id"] == "example"
    manifest["display_name"] = "Tampered"
    manifest_path.write_text(json.dumps(manifest))
    (cache / "state.json").write_text(
        json.dumps(
            {
                "targets": {
                    "providers/example.json": hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                }
            }
        )
    )
    with pytest.raises(SecurityError, match="TUF verification"):
        _load_cached(cache, trust_root)
