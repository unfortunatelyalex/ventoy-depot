import json
from pathlib import Path

import pytest

from ventoy_depot.security import SecurityError, load_and_validate_manifest, safe_filename


def manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "provider_id": "example-provider",
        "driver": "static-json",
        "allowed_hosts": ["example.org"],
        "metadata_url": "https://example.org/releases.json",
        "checksum_algorithm": "sha256",
        "detection": [{"regex": "^example-(?P<version>[0-9.]+)\\.iso$"}],
    }


def write_manifest(tmp_path: Path, value: dict[str, object]) -> Path:
    path = tmp_path / "provider.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_valid_declarative_manifest(tmp_path: Path) -> None:
    assert (
        load_and_validate_manifest(write_manifest(tmp_path, manifest()))["provider_id"]
        == "example-provider"
    )


@pytest.mark.parametrize(
    "name", ["../image.iso", "/image.iso", "folder/image.iso", "..\\image.iso"]
)
def test_provider_filename_cannot_escape(name: str) -> None:
    with pytest.raises(SecurityError):
        safe_filename(name)


def test_manifest_rejects_http(tmp_path: Path) -> None:
    value = manifest()
    value["metadata_url"] = "http://example.org/releases.json"
    with pytest.raises(SecurityError, match="HTTPS"):
        load_and_validate_manifest(write_manifest(tmp_path, value))


def test_manifest_rejects_short_fingerprint(tmp_path: Path) -> None:
    value = manifest()
    value["signer_fingerprints"] = ["DEADBEEF"]
    with pytest.raises(SecurityError, match="fingerprints"):
        load_and_validate_manifest(write_manifest(tmp_path, value))
