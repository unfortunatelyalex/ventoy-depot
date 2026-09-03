import json
from pathlib import Path

import pytest

from ventoy_depot.config import Settings
from ventoy_depot.models import IsoIdentity
from ventoy_depot.providers import provider_map
from ventoy_depot.providers.base import ProviderError
from ventoy_depot.providers.manifest import ManifestProvider
from ventoy_depot.registry_client import RegistrySnapshot
from ventoy_depot.security import SecurityError


def manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "provider_id": "example",
        "display_name": "Example",
        "homepage_url": "https://downloads.example.test/",
        "driver": "checksum-list",
        "allowed_hosts": ["downloads.example.test"],
        "capabilities": {
            "products": ["example-live"],
            "editions": ["desktop", "paid"],
            "flavors": [],
            "architectures": ["amd64"],
            "languages": [],
            "channels": ["stable"],
        },
        "detection": [
            {
                "regex": r"^example-(?P<edition>desktop|paid)-(?P<version>[0-9.]+)-amd64\.iso$",
                "identity": {
                    "product_id": "example-live",
                    "edition": "$group:edition",
                    "channel": "stable",
                    "architecture": "amd64",
                    "version": "$group:version",
                },
                "downloadable": True,
            }
        ],
        "release_sources": [
            {
                "source_id": "stable",
                "metadata_url": "https://downloads.example.test/SHA256SUMS",
                "artifact_regex": r"^example-(?P<edition>desktop)-(?P<version>[0-9.]+)-amd64\.iso$",
                "identity": {
                    "product_id": "example-live",
                    "edition": "desktop",
                    "channel": "stable",
                    "architecture": "amd64",
                },
                "download": {
                    "strategy": "url-template",
                    "url_template": "https://downloads.example.test/{filename}",
                },
                "verification": {
                    "level": "CHECKSUM",
                    "checksum": {"algorithm": "sha256", "strategy": "checksum-list"},
                },
            }
        ],
    }


def test_manifest_provider_detects_without_executing_code() -> None:
    detected = ManifestProvider(manifest()).detect(Path("example-desktop-2.1-amd64.iso"))
    assert detected is not None and detected.identity is not None
    assert detected.detection_source == "signed-registry-filename"
    assert detected.identity == IsoIdentity(
        "example", "example-live", "desktop", None, "stable", "amd64", None, "2.1", None
    )


def test_manifest_detection_regex_has_a_runtime_timeout() -> None:
    value = manifest()
    value["detection"] = [
        {
            "regex": r"(?P<version>(a+)+)\.iso",
            "identity": {
                "product_id": "example-live",
                "edition": "desktop",
                "channel": "stable",
                "architecture": "amd64",
                "version": "$group:version",
            },
            "downloadable": True,
        }
    ]

    detected = ManifestProvider(value).detect(Path(f"{'a' * 10_000}!.iso"))

    assert detected is None


def test_manifest_provider_rejects_identity_outside_capabilities() -> None:
    provider = ManifestProvider(manifest())
    identity = IsoIdentity(
        "example", "example-live", "server", None, "stable", "amd64", None, "1", None
    )
    with pytest.raises(ProviderError, match="edition"):
        provider.resolve(identity)


def test_manifest_provider_resolves_checksum_list_without_python_plugin(monkeypatch) -> None:
    value = manifest()
    value["allowed_hosts"] = ["downloads.example.test"]
    value["release_sources"] = [
        {
            "metadata_url": "https://downloads.example.test/SHA256SUMS",
            "artifact_regex": r"^example-(?P<edition>desktop)-(?P<version>[0-9.]+)-amd64\.iso$",
            "identity": {
                "product_id": "example-live",
                "edition": "desktop",
                "channel": "stable",
                "architecture": "amd64",
            },
            "download": {
                "strategy": "url-template",
                "url_template": "https://downloads.example.test/{filename}",
            },
            "verification": {
                "level": "CHECKSUM",
                "checksum": {"algorithm": "sha256", "strategy": "checksum-list"},
            },
        }
    ]

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://downloads.example.test/SHA256SUMS"
            return f"{'a' * 64}  example-desktop-2.1-amd64.iso\n".encode()

    monkeypatch.setattr("ventoy_depot.providers.manifest.SafeHttpClient", FakeClient)
    provider = ManifestProvider(value)
    installed = IsoIdentity(
        "example", "example-live", "desktop", None, "stable", "amd64", None, "1.0", None
    )
    artifact = provider.resolve(installed)

    assert artifact.version == "2.1"
    assert artifact.checksum == "a" * 64
    assert artifact.identity is not None
    assert artifact.identity.variant_key() == installed.variant_key()


def test_detection_only_manifest_variant_cannot_resolve() -> None:
    value = manifest()
    value["detection"][0]["downloadable"] = False  # type: ignore[index]
    provider = ManifestProvider(value)
    detected = provider.detect(Path("example-paid-2.1-amd64.iso"))
    assert detected is not None and detected.identity is not None
    with pytest.raises(ProviderError, match="not downloadable"):
        provider.resolve(detected.identity)


def test_signed_checksum_list_is_not_misrepresented_as_iso_signature(monkeypatch) -> None:
    value = manifest()
    value["allowed_hosts"] = ["downloads.example.test"]
    value["release_sources"] = [
        {
            "metadata_url": "https://downloads.example.test/SHA256SUMS",
            "artifact_regex": r"^example-(?P<edition>desktop)-(?P<version>[0-9.]+)-amd64\.iso$",
            "identity": {
                "product_id": "example-live",
                "edition": "desktop",
                "channel": "stable",
                "architecture": "amd64",
            },
            "download": {
                "strategy": "url-template",
                "url_template": "https://downloads.example.test/{filename}",
            },
            "verification": {
                "level": "SIGNED",
                "checksum": {"algorithm": "sha256", "strategy": "checksum-list"},
                "signature": {
                    "strategy": "signed-checksum-list",
                    "suffix": ".gpg",
                    "signer_fingerprints": ["A" * 40],
                },
            },
        }
    ]

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, _url: str) -> bytes:
            return f"{'a' * 64}  example-desktop-2.1-amd64.iso\n".encode()

    monkeypatch.setattr("ventoy_depot.providers.manifest.SafeHttpClient", FakeClient)
    provider = ManifestProvider(value)
    installed = IsoIdentity(
        "example", "example-live", "desktop", None, "stable", "amd64", None, "1", None
    )

    with pytest.raises(ProviderError, match="trusted provider keyring"):
        provider.resolve(installed)


def test_release_digest_uses_digest_bound_to_selected_asset(monkeypatch) -> None:
    value = manifest()
    value["allowed_hosts"] = ["api.example.test", "downloads.example.test"]
    value["release_sources"] = [
        {
            "metadata_url": "https://api.example.test/latest",
            "artifact_regex": r"^example-(?P<edition>desktop)-(?P<version>[0-9.]+)-amd64\.iso$",
            "identity": {
                "product_id": "example-live",
                "edition": "desktop",
                "channel": "stable",
                "architecture": "amd64",
            },
            "download": {"strategy": "release-asset"},
            "verification": {
                "level": "CHECKSUM",
                "checksum": {"algorithm": "sha256", "strategy": "release-digest"},
            },
        }
    ]
    filename = "example-desktop-2.2-amd64.iso"
    payload = {
        "assets": [
            {
                "name": filename,
                "browser_download_url": f"https://downloads.example.test/{filename}",
                "digest": f"sha256:{'b' * 64}",
                "size": 42,
            }
        ]
    }

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://api.example.test/latest"
            import json

            return json.dumps(payload).encode()

    monkeypatch.setattr("ventoy_depot.providers.manifest.SafeHttpClient", FakeClient)
    provider = ManifestProvider(value)
    installed = IsoIdentity(
        "example", "example-live", "desktop", None, "stable", "amd64", None, "1", None
    )
    artifact = provider.resolve(installed)
    assert artifact.checksum == "b" * 64
    assert artifact.size_bytes == 42


def test_explicit_local_manifest_is_loaded_and_marked_custom(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "example.json"
    path.write_text(json.dumps(manifest()), encoding="utf-8")
    monkeypatch.setattr(
        "ventoy_depot.providers.load_settings",
        lambda: Settings(local_manifests=(str(path),)),
    )
    monkeypatch.setattr(
        "ventoy_depot.registry_client.load_registry",
        lambda **_kwargs: RegistrySnapshot((), "bundled"),
    )

    provider = provider_map()["example"]

    assert provider.custom
    assert provider.origin == "custom"


def test_local_manifest_cannot_override_curated_provider(monkeypatch, tmp_path: Path) -> None:
    value = manifest()
    value["provider_id"] = "ubuntu"
    path = tmp_path / "ubuntu.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(
        "ventoy_depot.providers.load_settings",
        lambda: Settings(local_manifests=(str(path),)),
    )
    monkeypatch.setattr(
        "ventoy_depot.registry_client.load_registry",
        lambda **_kwargs: RegistrySnapshot((), "bundled"),
    )

    with pytest.raises(SecurityError, match="cannot override"):
        provider_map()


def test_local_manifest_symlink_is_rejected(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text(json.dumps(manifest()), encoding="utf-8")
    path = tmp_path / "enabled.json"
    path.symlink_to(target)
    monkeypatch.setattr(
        "ventoy_depot.providers.load_settings",
        lambda: Settings(local_manifests=(str(path),)),
    )
    monkeypatch.setattr(
        "ventoy_depot.registry_client.load_registry",
        lambda **_kwargs: RegistrySnapshot((), "bundled"),
    )

    with pytest.raises(SecurityError, match="symlink"):
        provider_map()
