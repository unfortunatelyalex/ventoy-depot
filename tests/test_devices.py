from pathlib import Path

import pytest

from ventoy_depot.devices import (
    DeviceError,
    _linux_devices,
    _stable_id_for_linux_mount,
    _windows_devices,
    is_ventoy_root,
    manual_device,
    revalidate_device,
)


def test_label_must_be_exactly_ventoy(tmp_path: Path) -> None:
    assert is_ventoy_root(tmp_path, "Ventoy") == (True, "volume-label")
    assert is_ventoy_root(tmp_path, "not-ventoy-backup") == (False, "")


def test_ventoy_efi_partition_is_never_a_data_volume(tmp_path: Path) -> None:
    (tmp_path / "ventoy").mkdir()

    assert is_ventoy_root(tmp_path, "VTOYEFI") == (False, "")


def test_manual_device_requires_a_ventoy_filesystem_marker(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "ventoy_depot.devices._manual_stable_identifier", lambda _path: "linux-uuid:test"
    )
    with pytest.raises(DeviceError, match="no Ventoy label or marker"):
        manual_device(tmp_path)

    (tmp_path / "ventoy").mkdir()
    device = manual_device(tmp_path)

    assert device.mount_path == tmp_path.resolve()
    assert device.identifier == "manual:linux-uuid:test"
    assert device.is_ventoy
    assert device.detection_reason == "ventoy-directory"


def test_manual_device_requires_stable_identifier(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "ventoy").mkdir()
    monkeypatch.setattr("ventoy_depot.devices._manual_stable_identifier", lambda _path: None)

    with pytest.raises(DeviceError, match="no stable device identifier"):
        manual_device(tmp_path)


def test_manual_device_revalidation_rejects_replaced_volume(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "ventoy").mkdir()
    identifiers = iter(("linux-uuid:first", "linux-uuid:replacement"))
    monkeypatch.setattr(
        "ventoy_depot.devices._manual_stable_identifier", lambda _path: next(identifiers)
    )
    selected = manual_device(tmp_path)

    with pytest.raises(DeviceError, match="identity changed"):
        revalidate_device(selected)


def test_manual_linux_identifier_prefers_filesystem_uuid(tmp_path: Path) -> None:
    payload = [
        {
            "serial": "disk-serial",
            "children": [{"mountpoint": str(tmp_path), "uuid": "volume-uuid", "serial": None}],
        }
    ]

    assert _stable_id_for_linux_mount(payload, tmp_path) == "linux-uuid:volume-uuid"


def test_manual_linux_identifier_falls_back_to_parent_disk_serial(tmp_path: Path) -> None:
    payload = [
        {
            "serial": "disk-serial",
            "children": [{"mountpoint": str(tmp_path), "uuid": None, "serial": None}],
        }
    ]

    assert _stable_id_for_linux_mount(payload, tmp_path) == "linux-serial:disk-serial"


def test_symlinked_ventoy_markers_are_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "ventoy").symlink_to(outside, target_is_directory=True)

    assert is_ventoy_root(root) == (False, "")


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
