from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path

from .models import Device


class DeviceError(RuntimeError):
    """A platform command could not enumerate supported removable media."""


def discover_ventoy_devices() -> list[Device]:
    system = platform.system()
    if system == "Linux":
        return _linux_devices()
    if system == "Windows":
        return _windows_devices()
    raise DeviceError(f"{system} is not supported. Linux and Windows are supported.")


def _is_ventoy_root(path: Path, label: str = "") -> bool:
    return (path / "ventoy").is_dir() or (path / ".ventoy").exists() or "ventoy" in label.lower()


def _linux_devices() -> list[Device]:
    try:
        result = subprocess.run(
            ["lsblk", "--json", "--bytes", "--output", "PATH,NAME,LABEL,MOUNTPOINT,SIZE,RM,TYPE"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise DeviceError("Could not run lsblk to inspect removable drives.") from error

    devices: list[Device] = []
    for disk in json.loads(result.stdout).get("blockdevices", []):
        if not disk.get("rm"):
            continue
        for partition in disk.get("children") or [disk]:
            mountpoint = partition.get("mountpoint")
            if partition.get("type") != "part" or not mountpoint:
                continue
            mount_path = Path(mountpoint)
            label = partition.get("label") or ""
            devices.append(
                Device(
                    identifier=partition["path"],
                    display_name=f"{partition['path']} ({label or partition['name']})",
                    mount_path=mount_path,
                    size_bytes=partition.get("size"),
                    is_removable=True,
                    is_ventoy=_is_ventoy_root(mount_path, label),
                )
            )
    return [device for device in devices if device.is_ventoy]


def _windows_devices() -> list[Device]:
    script = (
        "Get-Disk | Where-Object BusType -eq USB | ForEach-Object { "
        "$disk=$_; Get-Partition -DiskNumber $disk.Number | ForEach-Object { "
        "$part=$_; $vol=$part | Get-Volume; if ($vol.DriveLetter) { "
        "[PSCustomObject]@{Disk=$disk.Number;Label=$vol.FileSystemLabel;"
        "DriveLetter=$vol.DriveLetter;Size=$part.Size} } } } | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise DeviceError("Could not query USB volumes through PowerShell.") from error
    payload = result.stdout.strip()
    records = json.loads(payload) if payload else []
    if isinstance(records, dict):
        records = [records]
    devices: list[Device] = []
    for record in records:
        mount_path = Path(f"{record['DriveLetter']}:\\")
        label = record.get("Label") or ""
        devices.append(
            Device(
                identifier=f"Disk {record['Disk']}, {mount_path}",
                display_name=f"{mount_path} ({label or 'unlabelled'})",
                mount_path=mount_path,
                size_bytes=record.get("Size"),
                is_removable=True,
                is_ventoy=_is_ventoy_root(mount_path, label),
            )
        )
    return [device for device in devices if device.is_ventoy]
