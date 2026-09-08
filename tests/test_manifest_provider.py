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


def test_manifest_provider_formats_compact_detection_version() -> None:
    value = manifest()
    rule = value["detection"][0]  # type: ignore[index]
    rule["regex"] = r"^FD(?P<major>[0-9])(?P<minor>[0-9])LIVE\.iso$"  # type: ignore[index]
    rule["version_template"] = "{major}.{minor}"  # type: ignore[index]
    rule["identity"] = {  # type: ignore[index]
        "product_id": "example-live",
        "edition": "desktop",
        "channel": "stable",
        "architecture": "amd64",
    }

    detected = ManifestProvider(value).detect(Path("FD14LIVE.iso"))

    assert detected is not None and detected.identity is not None
    assert detected.identity.version == "1.4"


def test_manifest_provider_reports_automatic_download_capability() -> None:
    value = manifest()
    provider = ManifestProvider(value)
    assert provider.supports_automatic_download

    value["release_sources"] = []
    assert not ManifestProvider(value).supports_automatic_download

    value["release_sources"] = manifest()["release_sources"]
    value["release_sources"][0]["automatic_download"] = False  # type: ignore[index]
    assert not ManifestProvider(value).supports_automatic_download


def test_manifest_provider_normalizes_x86_dash_64_architecture() -> None:
    value = manifest()
    value["capabilities"]["architectures"] = ["x86_64"]  # type: ignore[index]
    value["detection"][0]["regex"] = (  # type: ignore[index]
        r"^example-(?P<edition>desktop|paid)-(?P<version>[0-9.]+)-"
        r"(?P<architecture>x86-64)\.iso$"
    )
    value["detection"][0]["identity"]["architecture"] = "$group:architecture"  # type: ignore[index]

    detected = ManifestProvider(value).detect(Path("example-desktop-2.1-x86-64.iso"))

    assert detected is not None and detected.identity is not None
    assert detected.identity.architecture == "x86_64"


def test_manifest_provider_can_require_iso_volume_metadata(tmp_path: Path) -> None:
    value = manifest()
    value["capabilities"]["architectures"] = ["amd64", "arm64"]  # type: ignore[index]
    value["detection"] = [
        {
            "regex": r"^install79\.iso$",
            "volume_regex": r"^OpenBSD/(?P<architecture>amd64|arm64)\s+7\.9 Install CD$",
            "identity": {
                "product_id": "example-live",
                "edition": "desktop",
                "channel": "stable",
                "architecture": "$group:architecture",
                "version": "7.9",
            },
            "downloadable": True,
        }
    ]
    iso = tmp_path / "install79.iso"
    descriptor = bytearray(2048)
    descriptor[0] = 1
    descriptor[1:6] = b"CD001"
    descriptor[6] = 1
    descriptor[40:72] = b"OpenBSD/arm64   7.9 Install CD".ljust(32, b" ")
    iso.write_bytes(bytes(16 * 2048) + descriptor)

    detected = ManifestProvider(value).detect(iso)

    assert detected is not None and detected.identity is not None
    assert detected.identity.architecture == "arm64"
    assert detected.identity.version == "7.9"
    assert detected.volume_id == "OpenBSD/arm64   7.9 Install CD"
    assert detected.detection_source.endswith("iso9660-volume-id")


def test_manifest_volume_detection_rejects_missing_metadata(tmp_path: Path) -> None:
    value = manifest()
    value["detection"][0]["regex"] = r"^install79\.iso$"  # type: ignore[index]
    value["detection"][0]["volume_regex"] = r"^OpenBSD/amd64\s+7\.9 Install CD$"  # type: ignore[index]
    path = tmp_path / "install79.iso"
    path.write_bytes(b"not an ISO")

    assert ManifestProvider(value).detect(path) is None


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


def test_manifest_provider_resolves_verified_zip_to_named_iso(monkeypatch) -> None:
    value = manifest()
    source = value["release_sources"][0]  # type: ignore[index]
    source["artifact_regex"] = (  # type: ignore[index]
        r"^example-(?P<edition>desktop)-(?P<major>[0-9])(?P<minor>[0-9])-amd64\.zip$"
    )
    source["version_template"] = "{major}.{minor}"  # type: ignore[index]
    source["archive"] = {  # type: ignore[index]
        "format": "zip",
        "member_template": "generic.iso",
        "output_filename_template": "{stem}.iso",
    }

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://downloads.example.test/SHA256SUMS"
            return f"{'c' * 64}  example-desktop-22-amd64.zip\n".encode()

    monkeypatch.setattr("ventoy_depot.providers.manifest.SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "example", "example-live", "desktop", None, "stable", "amd64", None, "1", None
    )

    artifact = ManifestProvider(value).resolve(installed)

    assert artifact.version == "2.2"
    assert artifact.filename == "example-desktop-22-amd64.iso"
    assert artifact.download_filename == "example-desktop-22-amd64.zip"
    assert artifact.archive_format == "zip"
    assert artifact.archive_member == "generic.iso"
    assert artifact.checksum == "c" * 64


def test_manifest_provider_reads_sourceforge_release_digest_and_size(monkeypatch) -> None:
    value = manifest()
    source = value["release_sources"][0]  # type: ignore[index]
    source["metadata_url"] = "https://downloads.example.test/best_release.json"  # type: ignore[index]
    source["artifact_regex"] = r"^ReactOS-(?P<version>[0-9.]+)-i386\.zip$"  # type: ignore[index]
    source["download"]["url_template"] = (  # type: ignore[index]
        "https://downloads.example.test/{filename}"
    )
    source["verification"]["checksum"] = {  # type: ignore[index]
        "algorithm": "sha256",
        "strategy": "release-digest",
    }
    source["archive"] = {  # type: ignore[index]
        "format": "zip",
        "member_template": "ReactOS-{version}-i386.iso",
        "output_filename_template": "ReactOS-{version}-i386.iso",
    }

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, _url: str) -> bytes:
            return json.dumps(
                {
                    "release": {
                        "filename": "/ReactOS/0.4.16/ReactOS-0.4.16-i386.zip",
                        "sha256sum": "d" * 64,
                        "bytes": 198_087_895,
                    }
                }
            ).encode()

    monkeypatch.setattr("ventoy_depot.providers.manifest.SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "example", "example-live", "desktop", None, "stable", "amd64", None, "0.4.15", None
    )

    artifact = ManifestProvider(value).resolve(installed)

    assert artifact.filename == "ReactOS-0.4.16-i386.iso"
    assert artifact.download_filename == "ReactOS-0.4.16-i386.zip"
    assert artifact.checksum == "d" * 64
    assert artifact.size_bytes == 198_087_895


def test_manifest_url_template_can_address_iso_named_directory(monkeypatch) -> None:
    value = manifest()
    source = value["release_sources"][0]  # type: ignore[index]
    source["download"]["url_template"] = (  # type: ignore[index]
        "https://downloads.example.test/{stem}/{filename}"
    )

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://downloads.example.test/SHA256SUMS"
            return f"{'a' * 64}  example-desktop-2.1-amd64.iso\n".encode()

    monkeypatch.setattr("ventoy_depot.providers.manifest.SafeHttpClient", FakeClient)
    artifact = ManifestProvider(value).resolve(
        IsoIdentity("example", "example-live", "desktop", None, "stable", "amd64", None, "1", None)
    )

    assert artifact.download_url == (
        "https://downloads.example.test/example-desktop-2.1-amd64/example-desktop-2.1-amd64.iso"
    )


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
