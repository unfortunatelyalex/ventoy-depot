from pathlib import Path

import pytest

from ventoy_iso_updater.iso import find_isos, identify_iso
from ventoy_iso_updater.models import Distro


@pytest.mark.parametrize(
    ("filename", "distro", "version", "architecture"),
    [
        ("ubuntu-24.04.2-desktop-amd64.iso", Distro.UBUNTU, "24.04.2", "amd64"),
        ("Fedora-Workstation-Live-x86_64-41-1.4.iso", Distro.FEDORA, "41", "x86_64"),
        ("debian-12.9.0-amd64-netinst.iso", Distro.DEBIAN, "12.9.0", "amd64"),
        ("archlinux-2025.01.01-x86_64.iso", Distro.ARCH, "2025.01.01", "x86_64"),
        ("linuxmint-22.1-cinnamon-64bit.iso", Distro.MINT, "22.1", "amd64"),
    ],
)
def test_identify_known_iso(filename: str, distro: Distro, version: str, architecture: str) -> None:
    iso = identify_iso(Path(filename))
    assert (iso.distro, iso.version, iso.architecture) == (distro, version, architecture)


def test_identify_unknown_iso() -> None:
    assert identify_iso(Path("rescue-image.iso")).distro == Distro.UNKNOWN


def test_find_isos_is_recursive_and_case_insensitive(tmp_path: Path) -> None:
    nested = tmp_path / "linux"
    nested.mkdir()
    (nested / "ubuntu-24.04-desktop-amd64.ISO").touch()
    (tmp_path / "not-an-iso.txt").touch()
    assert [iso.path.name for iso in find_isos(tmp_path)] == ["ubuntu-24.04-desktop-amd64.ISO"]
