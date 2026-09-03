from pathlib import Path

import pytest

from ventoy_depot.iso import identify_iso


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        (
            "debian-live-13.6.0-amd64-kde.iso",
            ("debian", "live", "kde", "stable", "amd64", "13.6.0", None),
        ),
        (
            "Fedora-Workstation-Live-44-1.7.x86_64.iso",
            ("fedora", "workstation", "live", "stable", "x86_64", "44", "1.7"),
        ),
        (
            "Fedora-Server-dvd-aarch64-44-1.4.iso",
            ("fedora", "server", "dvd", "stable", "aarch64", "44", "1.4"),
        ),
        (
            "Fedora-Silverblue-ostree-x86_64-44-1.4.iso",
            ("fedora", "silverblue", "ostree", "stable", "x86_64", "44", "1.4"),
        ),
        (
            "manjaro-kde-26.1.1-260825-linux71.iso",
            ("manjaro", "kde", "full", "stable", "x86_64", "26.1.1", "260825"),
        ),
        (
            "manjaro-gnome-26.1.0-rc3-minimal-260723-linux618.iso",
            ("manjaro", "gnome", "minimal", "review", "x86_64", "26.1.0-rc3", "260723"),
        ),
        (
            "Nobara-44-Steam-Handheld-2026-08-28.iso",
            ("nobara", "steam-handheld", None, "stable", "x86_64", "44", "2026-08-28"),
        ),
        (
            "ubuntu-25.10-live-server-arm64.iso",
            ("ubuntu", "live-server", None, "interim", "arm64", "25.10", None),
        ),
        (
            "Zorin-OS-17.3-Education-64-bit-r2.iso",
            ("zorin-os", "education", None, "stable", "x86_64", "17.3", "2"),
        ),
        (
            "gparted-live-1.7.0-1-amd64.iso",
            ("gparted-live", "live", None, "stable", "amd64", "1.7.0-1", None),
        ),
        (
            "kali-linux-2024.1-live-amd64.iso",
            ("kali-linux", "live", None, "stable", "amd64", "2024.1", None),
        ),
        (
            "nixos-plasma5-23.11.7202.e7cc61784ddf-x86_64-linux.iso",
            (
                "nixos",
                "graphical",
                "plasma5",
                "stable",
                "x86_64",
                "23.11.7202.e7cc61784ddf",
                None,
            ),
        ),
        (
            "VanillaOS-22.10-all.20231009.iso",
            ("vanilla-os", None, None, "stable", "amd64", "22.10", "20231009"),
        ),
        (
            "Win11_25H2_German_x64.iso",
            (
                "windows-11",
                "multi-edition",
                "consumer",
                "stable",
                "x86_64",
                "25H2",
                None,
            ),
        ),
    ],
)
def test_bundled_detection_matches_registry_fixture(
    filename: str, expected: tuple[str, str | None, str | None, str, str, str, str | None]
) -> None:
    identity = identify_iso(Path(filename)).identity
    assert identity is not None
    assert (
        identity.provider_id,
        identity.edition,
        identity.flavor,
        identity.channel,
        identity.architecture,
        identity.version,
        identity.build,
    ) == expected


@pytest.mark.parametrize(
    "filename",
    [
        "debian-live-13.6.0-amd64-unknown.iso",
        "pop-os_24.04_amd64_intel_27.iso",
        "Vanilla-OS-3-stable-amd64.iso",
    ],
)
def test_registry_counterexamples_remain_unknown(filename: str) -> None:
    assert identify_iso(Path(filename)).identity is None
