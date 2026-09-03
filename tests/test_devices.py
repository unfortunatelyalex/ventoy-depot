from pathlib import Path

import pytest

from ventoy_depot.devices import DeviceError, _linux_devices, _windows_devices, is_ventoy_root
from ventoy_iso_updater.devices import _is_ventoy_root


def test_ventoy_marker_is_detected(tmp_path: Path) -> None:
    (tmp_path / "ventoy").mkdir()
    assert _is_ventoy_root(tmp_path)


def test_ventoy_label_is_detected(tmp_path: Path) -> None:
    assert _is_ventoy_root(tmp_path, "Ventoy")


def test_generic_removable_drive_is_not_assumed_to_be_ventoy(tmp_path: Path) -> None:
    assert not _is_ventoy_root(tmp_path, "USB")


def test_label_must_be_exactly_ventoy(tmp_path: Path) -> None:
    assert is_ventoy_root(tmp_path, "Ventoy") == (True, "volume-label")
    assert is_ventoy_root(tmp_path, "not-ventoy-backup") == (False, "")


@pytest.mark.parametrize("payload", [[], "invalid", {"blockdevices": "invalid"}])
def test_linux_discovery_rejects_malformed_lsblk_json(monkeypatch, payload: object) -> None:
    monkeypatch.setattr("ventoy_depot.devices._run_json", lambda command, message: payload)
    with pytest.raises(DeviceError, match="unexpected response"):
        _linux_devices()


@pytest.mark.parametrize("payload", ["invalid", 7, ["invalid"]])
def test_windows_discovery_rejects_malformed_powershell_json(monkeypatch, payload: object) -> None:
    monkeypatch.setattr("ventoy_depot.devices._run_json", lambda command, message: payload)
    with pytest.raises(DeviceError, match="unexpected response|invalid volume"):
        _windows_devices()


def test_linux_discovery_excludes_device_without_stable_identifier(monkeypatch) -> None:
    payload = {
        "blockdevices": [
            {
                "rm": True,
                "children": [
                    {
                        "type": "part",
                        "mountpoint": "/media/ventoy",
                        "label": "Ventoy",
                        "path": "/dev/sdb1",
                        "name": "sdb1",
                    }
                ],
            }
        ]
    }
    monkeypatch.setattr("ventoy_depot.devices._run_json", lambda command, message: payload)

    assert _linux_devices() == []


def test_windows_discovery_excludes_volume_without_unique_id(monkeypatch) -> None:
    payload = {"DriveLetter": "E", "Disk": 2, "Label": "Ventoy", "Size": 1_000}
    monkeypatch.setattr("ventoy_depot.devices._run_json", lambda command, message: payload)

    assert _windows_devices() == []
