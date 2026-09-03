import json
from pathlib import Path

import pytest

from ventoy_depot.cli import main
from ventoy_depot.config import Settings, load_settings, save_settings


def test_settings_round_trip_explicit_local_manifest_paths(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    manifest = tmp_path / "provider.json"
    settings = Settings(language="de", local_manifests=(str(manifest),))

    save_settings(settings, config)

    assert load_settings(config) == settings


def test_settings_reject_relative_or_duplicate_local_manifest_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        Settings(local_manifests=("provider.json",))
    path = str(tmp_path / "provider.json")
    with pytest.raises(ValueError, match="unique"):
        Settings(local_manifests=(path, path))


def test_settings_reject_non_string_local_manifest_entry(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"schema_version": 1, "local_manifests": [42]}), encoding="utf-8")

    with pytest.raises(ValueError, match="list of absolute paths"):
        load_settings(config)


@pytest.mark.parametrize(
    "proxy",
    ["socks5://proxy.example", "http://user:secret@proxy.example", "proxy.example:8080"],
)
def test_settings_reject_unsupported_or_credentialed_proxy(proxy: str) -> None:
    with pytest.raises(ValueError, match="credential-free"):
        Settings(proxy=proxy)


def test_tui_startup_reports_invalid_settings_without_traceback(monkeypatch) -> None:
    def invalid_settings() -> None:
        raise ValueError("invalid settings")

    monkeypatch.setattr("ventoy_depot.cli.run_tui", invalid_settings)

    assert main([]) == 2
