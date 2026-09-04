from pathlib import Path

import pytest

from ventoy_depot.iso import identify_iso
from ventoy_depot.models import IsoIdentity
from ventoy_depot.providers import provider_map
from ventoy_depot.providers.base import ProviderError


@pytest.mark.parametrize(
    ("filename", "provider", "edition", "architecture"),
    [
        ("ubuntu-24.04.3-live-server-amd64.iso", "ubuntu", "live-server", "amd64"),
        ("debian-13.1.0-amd64-DVD-1.iso", "debian", "dvd-1", "amd64"),
        ("Fedora-KDE-Live-x86_64-42-1.1.iso", "fedora", "kde", "x86_64"),
        ("Fedora-Xfce-Live-44-1.7.x86_64.iso", "fedora", "xfce", "x86_64"),
        (
            "Fedora-MATE_Compiz-Live-44-1.7.x86_64.iso",
            "fedora",
            "mate_compiz",
            "x86_64",
        ),
        ("linuxmint-22.2-xfce-64bit.iso", "linux-mint", "xfce", "x86_64"),
        ("pop-os_24.04_amd64_nvidia_12.iso", "pop-os", "nvidia", "amd64"),
        ("Zorin-OS-17.3-Pro-64-bit.iso", "zorin-os", "pro", "x86_64"),
        ("clonezilla-live-3.3.3-15-amd64.iso", "clonezilla", "debian", "amd64"),
        ("clonezilla-live-20260705-resolute-amd64.iso", "clonezilla", "ubuntu", "amd64"),
        ("systemrescue-13.02-amd64.iso", "systemrescue", "live", "amd64"),
        ("proxmox-ve_9.2-1.iso", "proxmox", "installer", "amd64"),
        ("proxmox-ve_9.2-1-arm64.iso", "proxmox", "installer", "arm64"),
        ("rescuezilla-2.6.2-64bit.resolute.iso", "rescuezilla", "live", "amd64"),
        ("tails-amd64-7.11.iso", "tails", "iso", "amd64"),
        ("mt86plus_8.10_x86_64.grub.iso", "memtest86-plus", "grub", "x86_64"),
        ("alpine-standard-3.24.1-x86_64.iso", "alpine", "standard", "x86_64"),
        (
            "openSUSE-Tumbleweed-Rescue-CD-x86_64-Snapshot20260830-Media.iso",
            "opensuse-tumbleweed",
            "rescue-cd",
            "x86_64",
        ),
        ("FreeBSD-15.0-RELEASE-amd64-dvd1.iso", "freebsd", "dvd1", "amd64"),
        ("Rocky-9.8-x86_64-minimal.iso", "rocky-linux", "minimal", "x86_64"),
        ("AlmaLinux-10.2-aarch64-dvd.iso", "almalinux", "dvd", "aarch64"),
        ("grml-full-2026.04-amd64.iso", "grml", "full", "amd64"),
        ("Qubes-R4.3.1-x86_64.iso", "qubes-os", "installer", "x86_64"),
        ("netboot.xyz.iso", "netboot-xyz", "standard", "x86_64"),
        ("netboot.xyz-legacy.iso", "netboot-xyz", "legacy", "x86_64"),
        ("netboot.xyz-arm64.iso", "netboot-xyz", "standard", "arm64"),
        (
            "install-amd64-minimal-20260830T151604Z.iso",
            "gentoo",
            "minimal",
            "amd64",
        ),
        (
            "install-arm64-minimal-20260830T151604Z.iso",
            "gentoo",
            "minimal",
            "arm64",
        ),
        ("livegui-amd64-20260830T151604Z.iso", "gentoo", "livegui", "amd64"),
        ("HBCD_PE_x64.iso", "hirens-bootcd-pe", "pe", "x86_64"),
        (
            "shredos-2025.11_31_x86-64_v0.42_20260716.iso",
            "shredos",
            "standard",
            "x86_64",
        ),
        (
            "shredos-2025.11_31_i686_v0.42_20260716_lite_plus-partition.iso",
            "shredos",
            "lite",
            "i686",
        ),
        ("NetBSD-11.0-amd64.iso", "netbsd", "installer", "amd64"),
        ("NetBSD-11.0-i386.iso", "netbsd", "installer", "i386"),
        ("porteux-2.8-current-xfce-4.20-x86_64.iso", "porteux", "xfce", "x86_64"),
        ("GhostBSD-26.1-R15.0p2.iso", "ghostbsd", "mate", "amd64"),
        ("GhostBSD-26.1-R15.0p2-XFCE.iso", "ghostbsd", "xfce", "amd64"),
        ("GhostBSD-26.1-R15.0p2-GERSHWIN.iso", "ghostbsd", "gershwin", "amd64"),
        ("haiku-r1beta6-x86_64-anyboot.iso", "haiku", "anyboot", "x86_64"),
        ("haiku-r1beta6-x86_gcc2h-anyboot.iso", "haiku", "anyboot", "x86_gcc2h"),
        ("Solus-Budgie-Release-2026-04-18.iso", "solus", "budgie", "x86_64"),
        ("Solus-GNOME-Release-2026-04-18.iso", "solus", "gnome", "x86_64"),
        ("TrueNAS-SCALE-25.10.7.iso", "truenas", "community", "x86_64"),
        ("TrueNAS-26.0.0-BETA.3.iso", "truenas", "community", "x86_64"),
        ("neon-user-desktop-20260903-0454.iso", "kde-neon", "desktop", "x86_64"),
        ("neon-testing-desktop-20260901-0146.iso", "kde-neon", "desktop", "x86_64"),
        ("Parrot-home-7.3_amd64.iso", "parrot-os", "home", "amd64"),
        ("Parrot-spin-htb-7.3_amd64.iso", "parrot-os", "htb", "amd64"),
        ("void-live-x86_64-20250202-base.iso", "void-linux", "base", "x86_64"),
        ("void-live-aarch64-musl-20250202-xfce.iso", "void-linux", "xfce", "aarch64"),
        ("Mageia-10-x86_64.iso", "mageia", "classic", "x86_64"),
        ("Mageia-10-Live-Xfce-i686.iso", "mageia", "xfce", "i686"),
        (
            "CentOS-Stream-10-20260901.0-x86_64-boot.iso",
            "centos-stream",
            "boot",
            "x86_64",
        ),
        (
            "CentOS-Stream-9-latest-aarch64-dvd1.iso",
            "centos-stream",
            "dvd1",
            "aarch64",
        ),
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


def test_opensuse_current_alias_retains_variant_for_snapshot_update() -> None:
    detected = identify_iso(Path("openSUSE-Tumbleweed-KDE-Live-aarch64-Current.iso"))
    assert detected.identity is not None
    assert detected.identity.variant_key() == (
        "opensuse-tumbleweed",
        "opensuse-tumbleweed",
        "kde-live",
        None,
        "rolling",
        "aarch64",
        None,
    )


def test_historical_cachyos_kde_is_detected_but_requires_explicit_migration() -> None:
    detected = identify_iso(Path("cachyos-kde-linux-240512.iso"))
    assert detected.identity is not None
    assert detected.identity.edition == "kde"
    with pytest.raises(ProviderError, match="discontinued"):
        provider_map()["cachyos"].resolve(detected.identity)


def test_manual_assignment_cannot_invent_provider_channel(monkeypatch) -> None:
    def unexpected_resolve(*_args: object) -> object:
        raise AssertionError("resolver must not receive an unsupported identity")

    monkeypatch.setattr("ventoy_depot.providers.resolvers.resolve_release", unexpected_resolve)
    identity = IsoIdentity(
        "ubuntu", "ubuntu", "desktop", None, "nightly", "amd64", None, "24.04", None
    )
    with pytest.raises(ProviderError, match="channel"):
        provider_map()["ubuntu"].resolve(identity)


@pytest.mark.parametrize(
    ("identity", "message"),
    [
        (
            IsoIdentity(
                "fedora", "fedora", "workstation", "ostree", "stable", "x86_64", None, "44", None
            ),
            "do not form a supported variant",
        ),
        (
            IsoIdentity("debian", "debian", "netinst", "kde", "stable", "amd64", None, "13", None),
            "cannot carry a desktop flavor",
        ),
        (
            IsoIdentity("manjaro", "manjaro", "kde", None, "stable", "x86_64", None, "26.1", None),
            "explicit full or minimal",
        ),
    ],
)
def test_manual_assignment_cannot_combine_incompatible_variant_dimensions(
    identity: IsoIdentity, message: str
) -> None:
    with pytest.raises(ProviderError, match=message):
        provider_map()[identity.provider_id].resolve(identity)
