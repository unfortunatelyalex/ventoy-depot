from pathlib import Path

import pytest

from ventoy_depot.iso import identify_iso
from ventoy_depot.models import IsoIdentity
from ventoy_depot.providers import provider_map
from ventoy_depot.providers.base import ProviderError
from ventoy_depot.providers.builtin import BUILTIN_PROVIDERS


@pytest.mark.parametrize(
    ("filename", "provider", "edition", "architecture"),
    [
        ("ubuntu-24.04.3-live-server-amd64.iso", "ubuntu", "live-server", "amd64"),
        ("kubuntu-26.04.1-desktop-amd64.iso", "ubuntu-flavors", "desktop", "amd64"),
        ("lubuntu-25.10-desktop-amd64.iso", "ubuntu-flavors", "desktop", "amd64"),
        ("xubuntu-24.04.4-desktop-amd64.iso", "ubuntu-flavors", "desktop", "amd64"),
        ("ubuntu-budgie-26.04-desktop-amd64.iso", "ubuntu-flavors", "desktop", "amd64"),
        ("ubuntu-unity-26.04-desktop-amd64.iso", "ubuntu-flavors", "desktop", "amd64"),
        ("ubuntu-mate-24.04.4-desktop-amd64.iso", "ubuntu-flavors", "desktop", "amd64"),
        ("ubuntucinnamon-26.04.1-desktop-amd64.iso", "ubuntu-flavors", "desktop", "amd64"),
        ("edubuntu-26.04.1-desktop-amd64.iso", "ubuntu-flavors", "desktop", "amd64"),
        ("ubuntustudio-26.04.1-desktop-amd64.iso", "ubuntu-flavors", "desktop", "amd64"),
        ("ubuntukylin-26.04.1-desktop-amd64.iso", "ubuntu-flavors", "desktop", "amd64"),
        ("debian-13.1.0-amd64-DVD-1.iso", "debian", "dvd-1", "amd64"),
        (
            "devuan_excalibur_6.1.1_amd64_desktop-live.iso",
            "devuan",
            "desktop-live",
            "amd64",
        ),
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
        ("finnix-251.iso", "finnix", "live", "amd64"),
        ("alt-p10-rescue-20240309-i586.iso", "alt-rescue", "rescue", "i586"),
        (
            "alt-p11-rescue-live-20260612-x86_64.iso",
            "alt-rescue",
            "rescue-live",
            "x86_64",
        ),
        (
            "urbackup_restore_2.6.0.iso",
            "urbackup-restore",
            "restore",
            "x86_64",
        ),
        ("proxmox-ve_9.2-1.iso", "proxmox", "installer", "amd64"),
        ("proxmox-ve_9.2-1-arm64.iso", "proxmox", "installer", "arm64"),
        ("rescuezilla-2.6.2-64bit.resolute.iso", "rescuezilla", "live", "amd64"),
        ("tails-amd64-7.11.iso", "tails", "iso", "amd64"),
        ("mt86plus_8.10_x86_64.grub.iso", "memtest86-plus", "grub", "x86_64"),
        ("alpine-standard-3.24.1-x86_64.iso", "alpine", "standard", "x86_64"),
        (
            "chimera-linux-riscv64-LIVE-20251220-plasma.iso",
            "chimera-linux",
            "plasma",
            "riscv64",
        ),
        (
            "openSUSE-Tumbleweed-Rescue-CD-x86_64-Snapshot20260830-Media.iso",
            "opensuse-tumbleweed",
            "rescue-cd",
            "x86_64",
        ),
        ("openSUSE-Leap-15.6-DVD-x86_64-Media.iso", "opensuse-leap", "dvd", "x86_64"),
        (
            "Leap-16.0-online-installer-aarch64-Build178.27.install.iso",
            "opensuse-leap",
            "online",
            "aarch64",
        ),
        ("FreeBSD-15.0-RELEASE-amd64-dvd1.iso", "freebsd", "dvd1", "amd64"),
        ("OpenBSD-7.9-amd64-install.iso", "openbsd", "install", "amd64"),
        ("Rocky-9.8-x86_64-minimal.iso", "rocky-linux", "minimal", "x86_64"),
        ("AlmaLinux-10.2-aarch64-dvd.iso", "almalinux", "dvd", "aarch64"),
        ("OracleLinux-R10-U2-x86_64-dvd.iso", "oracle-linux", "dvd", "x86_64"),
        ("OracleLinux-R10-U2-x86_64-boot.iso", "oracle-linux", "boot", "x86_64"),
        ("OracleLinux-R9-U8-aarch64-boot-uek.iso", "oracle-linux", "boot-uek", "aarch64"),
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
        ("OI-hipster-gui-20260430.iso", "openindiana", "gui", "x86_64"),
        ("OI-hipster-text-20260430.iso", "openindiana", "text", "x86_64"),
        ("OI-hipster-minimal-20260430.iso", "openindiana", "minimal", "x86_64"),
        ("xcp-ng-8.3.0-20260806.iso", "xcp-ng", "full", "x86_64"),
        ("xcp-ng-8.3.0-20260806-netinstall.iso", "xcp-ng", "netinstall", "x86_64"),
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
        ("Win10_22H2_German_x64v1.iso", "windows-10", "multi-edition", "x86_64"),
        ("Win10_22H2_English_x32v1.iso", "windows-10", "multi-edition", "x86"),
        ("SERVER_EVAL_x64FRE_de-de.iso", "windows-server", "evaluation", "x86_64"),
        (
            "26100.1742.240906-0331.ge_release_svc_refresh_SERVER_EVAL_x64FRE_en-us.iso",
            "windows-server",
            "evaluation",
            "x86_64",
        ),
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


def test_openbsd_official_name_requires_matching_volume_id(tmp_path: Path) -> None:
    provider = next(item for item in BUILTIN_PROVIDERS if item.provider_id == "openbsd")
    path = tmp_path / "install79.iso"
    descriptor = bytearray(2048)
    descriptor[0] = 1
    descriptor[1:6] = b"CD001"
    descriptor[6] = 1
    descriptor[40:72] = b"OpenBSD/arm64   7.9 Install CD".ljust(32, b" ")
    path.write_bytes(bytes(16 * 2048) + descriptor)

    detected = identify_iso(path, (provider,))

    assert detected.identity == IsoIdentity(
        "openbsd", "openbsd", "install", None, "release", "arm64", None, "7.9", None
    )
    assert detected.detection_source == "filename+iso9660-volume-id"


def test_openbsd_official_name_rejects_version_mismatch(tmp_path: Path) -> None:
    provider = next(item for item in BUILTIN_PROVIDERS if item.provider_id == "openbsd")
    path = tmp_path / "install78.iso"
    descriptor = bytearray(2048)
    descriptor[0] = 1
    descriptor[1:6] = b"CD001"
    descriptor[6] = 1
    descriptor[40:72] = b"OpenBSD/amd64   7.9 Install CD".ljust(32, b" ")
    path.write_bytes(bytes(16 * 2048) + descriptor)

    assert identify_iso(path, (provider,)).identity is None


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
