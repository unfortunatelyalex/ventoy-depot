from pathlib import Path

import pytest

from ventoy_depot.iso import identify_iso


@pytest.mark.parametrize(
    ("filename", "provider", "edition", "architecture"),
    [
        ("ubuntu-24.04.3-live-server-amd64.iso", "ubuntu", "live-server", "amd64"),
        ("debian-13.1.0-amd64-DVD-1.iso", "debian", "dvd-1", "amd64"),
        ("Fedora-KDE-Live-x86_64-42-1.1.iso", "fedora", "kde", "x86_64"),
        ("linuxmint-22.2-xfce-64bit.iso", "linux-mint", "xfce", "amd64"),
        ("pop-os_24.04_amd64_nvidia_12.iso", "pop-os", "nvidia", "amd64"),
        ("Zorin-OS-17.3-Pro-64-bit.iso", "zorin-os", "pro", "amd64"),
    ],
)
def test_variant_preserving_detection(
    filename: str, provider: str, edition: str, architecture: str
) -> None:
    detected = identify_iso(Path(filename))
    assert detected.identity is not None
    assert (
        detected.identity.provider_id,
        detected.identity.edition,
        detected.identity.architecture,
    ) == (provider, edition, architecture)


def test_unknown_filename_is_not_guessed() -> None:
    assert identify_iso(Path("renamed.iso")).identity is None
