import hashlib
import json
from pathlib import Path

from ventoy_depot.cli import main
from ventoy_depot.models import DetectedIso, IsoIdentity, ReleaseArtifact
from ventoy_depot.providers.base import Provider, ProviderCapabilities


class HealthyProvider(Provider):
    provider_id = "healthy"
    display_name = "Healthy"
    capabilities = ProviderCapabilities(("live",), ("amd64",), (), ("stable",))

    @property
    def products(self) -> tuple[str, ...]:
        return ("healthy",)

    def detect(self, path: Path) -> DetectedIso | None:
        return None

    def resolve(self, identity: IsoIdentity) -> ReleaseArtifact:
        return ReleaseArtifact(
            "2",
            None,
            "healthy-2.iso",
            "https://example.test/healthy-2.iso",
            1,
            "sha256",
            "a" * 64,
            None,
            (),
            frozenset({"example.test"}),
            IsoIdentity(
                identity.provider_id,
                identity.product_id,
                identity.edition,
                identity.flavor,
                identity.channel,
                identity.architecture,
                identity.language,
                "2",
                None,
            ),
        )


def test_verify_compares_current_recognized_iso_with_official_checksum(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    path = tmp_path / "healthy-2.iso"
    path.write_bytes(b"current")
    identity = IsoIdentity("healthy", "healthy", "live", None, "stable", "amd64", None, "2", None)
    provider = HealthyProvider()
    expected = hashlib.sha256(b"current").hexdigest()

    def resolve(assigned: IsoIdentity) -> ReleaseArtifact:
        return ReleaseArtifact(
            "2",
            None,
            path.name,
            "https://example.test/healthy-2.iso",
            path.stat().st_size,
            "sha256",
            expected,
            None,
            (),
            frozenset({"example.test"}),
            assigned,
        )

    monkeypatch.setattr(provider, "resolve", resolve)
    monkeypatch.setattr(
        "ventoy_depot.cli.identify_iso",
        lambda selected: DetectedIso(selected, identity, 1.0, "fixture"),
    )
    monkeypatch.setattr("ventoy_depot.cli.provider_map", lambda: {"healthy": provider})

    assert main(["verify", str(path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["data"]["verified"] is True
    assert payload["data"]["expected"] == expected


def test_verify_returns_distinct_exit_code_for_official_checksum_mismatch(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    path = tmp_path / "healthy-2.iso"
    path.write_bytes(b"tampered")
    identity = IsoIdentity("healthy", "healthy", "live", None, "stable", "amd64", None, "2", None)
    provider = HealthyProvider()
    monkeypatch.setattr(
        "ventoy_depot.cli.identify_iso",
        lambda selected: DetectedIso(selected, identity, 1.0, "fixture"),
    )
    monkeypatch.setattr("ventoy_depot.cli.provider_map", lambda: {"healthy": provider})

    assert main(["verify", str(path), "--json"]) == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["verified"] is False


def test_verify_still_hashes_when_official_metadata_is_unavailable(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    path = tmp_path / "healthy-1.iso"
    path.write_bytes(b"historical")
    identity = IsoIdentity("healthy", "healthy", "live", None, "stable", "amd64", None, "1", None)
    provider = HealthyProvider()

    def unavailable(_identity: IsoIdentity) -> ReleaseArtifact:
        raise OSError("offline")

    monkeypatch.setattr(provider, "resolve", unavailable)
    monkeypatch.setattr(
        "ventoy_depot.cli.identify_iso",
        lambda selected: DetectedIso(selected, identity, 1.0, "fixture"),
    )
    monkeypatch.setattr("ventoy_depot.cli.provider_map", lambda: {"healthy": provider})

    assert main(["verify", str(path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["verified"] is None
    assert payload["data"]["official_metadata_error"] == "offline"


def test_provider_doctor_checks_selected_provider_network_metadata(monkeypatch, capsys) -> None:
    monkeypatch.setattr("ventoy_depot.cli.provider_map", lambda: {"healthy": HealthyProvider()})

    assert main(["providers", "doctor", "healthy", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"][0] == {
        "provider_id": "healthy",
        "origin": "bundled",
        "custom": False,
        "status": "healthy",
        "network_checked": True,
        "version": "2",
        "filename": "healthy-2.iso",
        "verification_level": "checksum",
    }


def test_provider_doctor_all_is_fast_configuration_check(monkeypatch, capsys) -> None:
    provider = HealthyProvider()

    def unexpected_resolve(_identity: IsoIdentity) -> ReleaseArtifact:
        raise AssertionError("default all-provider doctor must not contact networks")

    monkeypatch.setattr(provider, "resolve", unexpected_resolve)
    monkeypatch.setattr("ventoy_depot.cli.provider_map", lambda: {"healthy": provider})

    assert main(["providers", "doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"][0]["status"] == "configured"
    assert payload["data"][0]["network_checked"] is False


def test_provider_doctor_reports_failed_selected_probe(monkeypatch, capsys) -> None:
    provider = HealthyProvider()

    def unavailable(_identity: IsoIdentity) -> ReleaseArtifact:
        raise OSError("metadata host unavailable")

    monkeypatch.setattr(provider, "resolve", unavailable)
    monkeypatch.setattr("ventoy_depot.cli.provider_map", lambda: {"healthy": provider})

    assert main(["providers", "doctor", "healthy", "--json"]) == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"][0]["status"] == "unavailable"
    assert payload["data"][0]["network_checked"] is True
    assert payload["data"][0]["error"] == "metadata host unavailable"
