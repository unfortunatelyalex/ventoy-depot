from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .models import Device


class DeviceError(RuntimeError):
    pass


def is_ventoy_root(path: Path, label: str = "") -> tuple[bool, str]:
    normalized_label = label.strip().casefold()
    if normalized_label == "vtoyefi":
        return False, ""
    if normalized_label == "ventoy":
        return True, "volume-label"
    directory_marker = path / "ventoy"
    file_marker = path / ".ventoy"
    if not directory_marker.is_symlink() and directory_marker.is_dir():
        return True, "ventoy-directory"
    if not file_marker.is_symlink() and file_marker.exists():
        return True, "ventoy-marker"
    return False, ""


def manual_device(mount_path: Path) -> Device:
    resolved = mount_path.resolve(strict=True)
    valid, reason = is_ventoy_root(resolved)
    if not valid:
        raise DeviceError("The selected path has no Ventoy label or marker.")
    stable = _manual_stable_identifier(resolved)
    if stable is None:
        raise DeviceError("The selected Ventoy volume has no stable device identifier.")
    usage = shutil.disk_usage(resolved)
    return Device(
        f"manual:{stable}",
        str(resolved),
        resolved,
        usage.total,
        usage.free,
        False,
        True,
        reason,
    )


def discover_ventoy_devices() -> list[Device]:
    system = platform.system()
    if system == "Linux":
        return _linux_devices()
    if system == "Windows":
        return _windows_devices()
    raise DeviceError(f"{system} is unsupported; use Linux or Windows.")


def find_device(identifier: str) -> Device:
    for device in discover_ventoy_devices():
        if device.identifier == identifier or str(device.mount_path) == identifier:
            return device
    candidate = Path(identifier)
    if candidate.exists():
        return manual_device(candidate)
    raise DeviceError(f"Ventoy device not found: {identifier}")


def revalidate_device(device: Device) -> Device:
    current = (
        manual_device(device.mount_path)
        if not device.is_removable
        else find_device(device.identifier)
    )
    if current.identifier != device.identifier:
        raise DeviceError("The device identity changed during the operation.")
    if current.mount_path.resolve() != device.mount_path.resolve():
        raise DeviceError("The device mountpoint changed during the operation.")
    return current


def _manual_stable_identifier(path: Path) -> str | None:
    system = platform.system()
    if system == "Linux":
        output = _run_json(
            ["lsblk", "--json", "--output", "NAME,MOUNTPOINT,UUID,SERIAL"],
            "Could not determine a stable identifier for the selected volume.",
        )
        records = output.get("blockdevices") if isinstance(output, dict) else None
        if not isinstance(records, list):
            raise DeviceError("lsblk returned an unexpected response.")
        return _stable_id_for_linux_mount(records, path)
    if system == "Windows":
        drive = path.drive.rstrip(":")
        if len(drive) != 1 or not drive.isalpha():
            return None
        script = (
            f"$part=Get-Partition -DriveLetter '{drive}' -ErrorAction Stop; "
            "$disk=Get-Disk -Number $part.DiskNumber -ErrorAction Stop; "
            "[PSCustomObject]@{UniqueId=$disk.UniqueId} | ConvertTo-Json -Compress"
        )
        output = _run_json(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            "Could not determine a stable identifier for the selected volume.",
        )
        unique_id = output.get("UniqueId") if isinstance(output, dict) else None
        return (
            f"windows:{unique_id.strip()}"
            if isinstance(unique_id, str) and unique_id.strip()
            else None
        )
    return None


def _stable_id_for_linux_mount(
    records: list[Any], path: Path, inherited_serial: str | None = None
) -> str | None:
    expected = path.resolve()
    for record in records:
        if not isinstance(record, dict):
            continue
        serial = record.get("serial")
        effective_serial = (
            serial.strip() if isinstance(serial, str) and serial.strip() else inherited_serial
        )
        mountpoint = record.get("mountpoint")
        if isinstance(mountpoint, str) and mountpoint:
            try:
                matches = Path(mountpoint).resolve() == expected
            except OSError:
                matches = False
            if matches:
                uuid = record.get("uuid")
                if isinstance(uuid, str) and uuid.strip():
                    return f"linux-uuid:{uuid.strip()}"
                if effective_serial:
                    return f"linux-serial:{effective_serial}"
        children = record.get("children")
        if isinstance(children, list):
            found = _stable_id_for_linux_mount(children, path, effective_serial)
            if found is not None:
                return found
    return None


def _linux_devices() -> list[Device]:
    output = _run_json(
        [
            "lsblk",
            "--json",
            "--bytes",
            "--output",
            "PATH,NAME,LABEL,MOUNTPOINT,SIZE,RM,HOTPLUG,TRAN,TYPE,SERIAL,UUID",
        ],
        "Could not run lsblk to inspect removable drives.",
    )
    if not isinstance(output, dict) or not isinstance(output.get("blockdevices"), list):
        raise DeviceError("lsblk returned an unexpected response.")
    devices: list[Device] = []
    for disk in output["blockdevices"]:
        if not isinstance(disk, dict):
            raise DeviceError("lsblk returned an invalid device record.")
        eligible = bool(disk.get("rm") or disk.get("hotplug") or disk.get("tran") == "usb")
        if not eligible:
            continue
        children = disk.get("children")
        if children is not None and not isinstance(children, list):
            raise DeviceError("lsblk returned invalid partition data.")
        for partition in children or [disk]:
            if not isinstance(partition, dict):
                raise DeviceError("lsblk returned an invalid partition record.")
            mountpoint = partition.get("mountpoint")
            if (
                partition.get("type") not in {"part", "disk"}
                or not isinstance(mountpoint, str)
                or not mountpoint
            ):
                continue
            path = Path(mountpoint)
            label = partition.get("label") or ""
            valid, reason = is_ventoy_root(path, label)
            if not valid:
                continue
            stable = partition.get("uuid") or disk.get("serial")
            if not isinstance(stable, str) or not stable.strip():
                continue
            try:
                free = shutil.disk_usage(path).free
            except OSError:
                free = None
            partition_path = partition.get("path")
            partition_name = partition.get("name")
            if not isinstance(partition_path, str) or not isinstance(partition_name, str):
                raise DeviceError("lsblk device record is missing its path or name.")
            devices.append(
                Device(
                    str(stable),
                    f"{partition_path} ({label or partition_name})",
                    path,
                    partition.get("size"),
                    free,
                    True,
                    True,
                    reason,
                )
            )
    return devices


def _windows_devices() -> list[Device]:
    script = (
        "Get-Disk | Where-Object BusType -eq USB | ForEach-Object { $disk=$_; "
        "Get-Partition -DiskNumber $disk.Number | ForEach-Object { $part=$_; "
        "$vol=$part | Get-Volume -ErrorAction SilentlyContinue; if ($vol -and $vol.DriveLetter) { "
        "[PSCustomObject]@{Disk=$disk.Number;UniqueId=$disk.UniqueId;Label=$vol.FileSystemLabel;"
        "DriveLetter=$vol.DriveLetter;Size=$part.Size} } } } | ConvertTo-Json -Compress"
    )
    output = _run_json(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        "Could not query USB volumes through PowerShell.",
    )
    if isinstance(output, dict) and "DriveLetter" in output:
        records = [output]
    elif isinstance(output, list):
        records = output
    elif output in ({}, None):
        records = []
    else:
        raise DeviceError("PowerShell returned an unexpected response.")
    devices: list[Device] = []
    for record in records:
        if not isinstance(record, dict):
            raise DeviceError("PowerShell returned an invalid volume record.")
        drive_letter = record.get("DriveLetter")
        if not isinstance(drive_letter, str) or len(drive_letter) != 1:
            raise DeviceError("PowerShell volume record has no valid drive letter.")
        path = Path(f"{drive_letter}:\\")
        label = record.get("Label") or ""
        valid, reason = is_ventoy_root(path, label)
        if valid:
            unique_id = record.get("UniqueId")
            if not isinstance(unique_id, str) or not unique_id.strip():
                continue
            try:
                free = shutil.disk_usage(path).free
            except OSError:
                free = None
            devices.append(
                Device(
                    unique_id,
                    f"{path} ({label or 'unlabelled'})",
                    path,
                    record.get("Size"),
                    free,
                    True,
                    True,
                    reason,
                )
            )
    return devices


def _run_json(command: list[str], message: str) -> Any:
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return json.loads(result.stdout or "{}")
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise DeviceError(message) from error
