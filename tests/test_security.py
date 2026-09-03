import json
from pathlib import Path

import pytest

from ventoy_depot.security import SecurityError, load_and_validate_manifest, safe_filename


def manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "provider_id": "example-provider",
        "display_name": "Example Provider",
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
                "artifact_regex": "^example-(?P<version>[0-9.]+)\\.iso$",
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
                    "checksum": {"algorithm": "sha256", "strategy": "checksum-list"},
                },
            }
        ],
        "detection": [
            {
                "regex": "^example-(?P<version>[0-9.]+)\\.iso$",
                "identity": {
                    "product_id": "example",
                    "channel": "stable",
                    "architecture": "x86_64",
                },
                "downloadable": True,
            }
        ],
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
    value["homepage_url"] = "http://example.org/"
    with pytest.raises(SecurityError, match="HTTPS"):
        load_and_validate_manifest(write_manifest(tmp_path, value))


def test_manifest_rejects_short_fingerprint(tmp_path: Path) -> None:
    value = manifest()
    source = value["release_sources"][0]  # type: ignore[index]
    source["verification"]["signature"] = {  # type: ignore[index]
        "strategy": "sidecar",
        "signer_fingerprints": ["DEADBEEF"],
    }
    with pytest.raises(SecurityError, match="fingerprints"):
        load_and_validate_manifest(write_manifest(tmp_path, value))


def test_manifest_rejects_nested_http_url(tmp_path: Path) -> None:
    value = manifest()
    source = value["release_sources"][0]  # type: ignore[index]
    source["download"]["url_template"] = "http://example.org/{filename}"  # type: ignore[index]
    with pytest.raises(SecurityError, match="HTTPS"):
        load_and_validate_manifest(write_manifest(tmp_path, value))


def test_manifest_rejects_nested_short_fingerprint(tmp_path: Path) -> None:
    value = manifest()
    source = value["release_sources"][0]  # type: ignore[index]
    source["verification"]["signature"] = {  # type: ignore[index]
        "strategy": "sidecar",
        "signer_fingerprints": ["DEADBEEF"],
    }
    with pytest.raises(SecurityError, match="fingerprints"):
        load_and_validate_manifest(write_manifest(tmp_path, value))


def test_manifest_rejects_nested_repetition_regex(tmp_path: Path) -> None:
    value = manifest()
    value["detection"][0]["regex"] = r"^(\d+)+$"  # type: ignore[index]
    with pytest.raises(SecurityError, match="unsafe"):
        load_and_validate_manifest(write_manifest(tmp_path, value))


def test_manifest_rejects_nested_unsafe_artifact_regex(tmp_path: Path) -> None:
    value = manifest()
    value["release_sources"][0]["artifact_regex"] = r"^(\d+)+$"  # type: ignore[index]
    with pytest.raises(SecurityError, match="unsafe"):
        load_and_validate_manifest(write_manifest(tmp_path, value))


def test_manifest_rejects_url_path_traversal(tmp_path: Path) -> None:
    value = manifest()
    value["release_sources"][0]["metadata_url"] = (  # type: ignore[index]
        "https://example.org/releases/../private"
    )
    with pytest.raises(SecurityError, match="traversal"):
        load_and_validate_manifest(write_manifest(tmp_path, value))


def test_manifest_rejects_old_incomplete_shape(tmp_path: Path) -> None:
    value = {
        "schema_version": 1,
        "provider_id": "example-provider",
        "driver": "static-json",
        "allowed_hosts": ["example.org"],
        "detection": [{"regex": "example"}],
    }
    with pytest.raises(SecurityError, match="missing fields"):
        load_and_validate_manifest(write_manifest(tmp_path, value))


@pytest.mark.parametrize("host", [7, "-example.org", "example..org"])
def test_manifest_rejects_invalid_host_entries(tmp_path: Path, host: object) -> None:
    value = manifest()
    value["allowed_hosts"] = [host]
    with pytest.raises(SecurityError, match="host allow-list"):
        load_and_validate_manifest(write_manifest(tmp_path, value))


def test_manifest_rejects_case_insensitive_duplicate_hosts(tmp_path: Path) -> None:
    value = manifest()
    value["allowed_hosts"] = ["example.org", "EXAMPLE.ORG"]
    with pytest.raises(SecurityError, match="duplicate"):
        load_and_validate_manifest(write_manifest(tmp_path, value))


def test_manifest_identity_must_be_declared_in_capabilities(tmp_path: Path) -> None:
    value = manifest()
    value["detection"][0]["identity"]["architecture"] = "aarch64"  # type: ignore[index]
    with pytest.raises(SecurityError, match="not declared"):
        load_and_validate_manifest(write_manifest(tmp_path, value))


def test_bundled_schema_matches_registry_contract() -> None:
    schema_path = (
        Path(__file__).parents[1] / "src" / "ventoy_depot" / "registry" / "provider-v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert set(schema["required"]) == {
        "schema_version",
        "provider_id",
        "display_name",
        "homepage_url",
        "driver",
        "allowed_hosts",
        "capabilities",
        "release_sources",
        "detection",
    }
    assert (
        schema["$defs"]["signature"]["properties"]["signer_fingerprints"]["items"]["pattern"]
        == "^(?:[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64})$"
    )
