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
        ("adelie-inst-x86_64-1.0-beta6-20241223.iso", "adelie-linux", "inst", "x86_64"),
        (
            "adelie-live-kde-aarch64-1.0-beta6-20241223.iso",
            "adelie-linux",
            "live",
            "aarch64",
        ),
        ("KaOS-DINIT-2026.06-x86_64.iso", "kaos", "dinit", "x86_64"),
        ("KaOS-2025.09-x86_64.iso", "kaos", "systemd", "x86_64"),
        ("ubuntu-24.04.3-live-server-amd64.iso", "ubuntu", "live-server", "amd64"),
        ("artix-base-openrc-20260813-x86_64.iso", "artix-linux", "base", "x86_64"),
        ("backbox-9-desktop-amd64.iso", "backbox", "desktop", "amd64"),
        (
            "artix-stable-plasma-dinit-20260813-x86_64.iso",
            "artix-linux",
            "plasma",
            "x86_64",
        ),
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
        (
            "fedora-coreos-stable-44.20260817.3.2-live-iso.x86_64.iso",
            "fedora-coreos",
            "live-iso",
            "x86_64",
        ),
        ("flatcar-stable-4593.2.5-amd64.iso", "flatcar", "live-iso", "amd64"),
        ("linuxmint-22.2-xfce-64bit.iso", "linux-mint", "xfce", "x86_64"),
        ("pop-os_24.04_amd64_nvidia_12.iso", "pop-os", "nvidia", "amd64"),
        ("Zorin-OS-17.3-Pro-64-bit.iso", "zorin-os", "pro", "x86_64"),
        ("clonezilla-live-3.3.3-15-amd64.iso", "clonezilla", "debian", "amd64"),
        ("clonezilla-live-20260705-resolute-amd64.iso", "clonezilla", "ubuntu", "amd64"),
        ("systemrescue-13.02-amd64.iso", "systemrescue", "live", "amd64"),
        ("ipfire-2.29-core202-aarch64.iso", "ipfire", "installer", "aarch64"),
        ("OPNsense-26.7-dvd-amd64.iso", "opnsense", "dvd", "amd64"),
        ("pfSense-CE-2.8.1-RELEASE-amd64.iso", "pfsense-ce", "dvd", "amd64"),
        ("redorescue-4.0.0.iso", "redo-rescue", "live", "amd64"),
        ("ubcd539.iso", "ultimate-boot-cd", "diagnostics", "x86"),
        (
            "supergrub2-classic-2.06s4-multiarch-CD.iso",
            "super-grub2-disk",
            "multiarch",
            "multiarch",
        ),
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
        ("FD14LIVE.iso", "freedos", "livecd", "i386"),
        ("FD14LGCY.iso", "freedos", "legacycd", "i386"),
        ("ReactOS-0.4.16-i386.iso", "reactos", "unified", "i386"),
        ("deepin-desktop-community-25.2.0-amd64.iso", "deepin", "desktop-community", "amd64"),
        (
            "deepin-desktop-community-25.2.0-riscv64.iso",
            "deepin",
            "desktop-community",
            "riscv64",
        ),
        (
            "garuda-dr460nized-gaming-linux-garuda-260819.iso",
            "garuda-linux",
            "dr460nized-gaming",
            "x86_64",
        ),
        ("garuda-xfce-linux-lts-260819.iso", "garuda-linux", "xfce", "x86_64"),
        ("sparkylinux-8.4-x86_64-kde.iso", "sparkylinux", "kde", "x86_64"),
        (
            "sparkylinux-8.4-i686-pae-minimalcli.iso",
            "sparkylinux",
            "minimalcli",
            "i686-pae",
        ),
        ("drift-linux-FAST-hybrid.iso", "drift-linux", "fast", "x86_64"),
        ("drift-linux-FAST-XS-hybrid.iso", "drift-linux", "fast-xs", "x86_64"),
        ("linux-lite-8.0-64bit.iso", "linux-lite", "desktop", "x86_64"),
        ("tsurugi_linux_26.03.iso", "tsurugi-linux", "lab", "x86_64"),
        ("tsurugi_acquire_2021.1.iso", "tsurugi-linux", "acquire", "i386"),
        ("archbang-050926-x86_64.iso", "archbang", "desktop", "x86_64"),
        ("archbang-220826.iso", "archbang", "desktop", "x86_64"),
        ("BookwormPup64_10.0.12.iso", "puppy-linux", "bookwormpup64", "x86_64"),
        ("bodhi-7.0.0-64.iso", "bodhi-linux", "standard", "x86_64"),
        ("bodhi-7.0.0-64-hwe.iso", "bodhi-linux", "hwe", "x86_64"),
        ("bodhi-7.0.0-64-s76.iso", "bodhi-linux", "s76", "x86_64"),
        ("bodhi-7.0.0-64-apppack.iso", "bodhi-linux", "apppack", "x86_64"),
        ("bodhi-5.1.0-legacy.iso", "bodhi-linux", "legacy", "i386"),
        ("boot-repair-disk-64bit.iso", "boot-repair-disk", "live", "x86_64"),
        ("blackarch-linux-full-2026.09.01-x86_64.iso", "blackarch", "full", "x86_64"),
        ("q4os-6.8-x64.r1.iso", "q4os", "plasma-live", "x86_64"),
        ("q4os-6.8-x64-tde.r1.iso", "q4os", "trinity-live", "x86_64"),
        ("q4os-6.8-x64-instcd.r1.iso", "q4os", "trinity-install", "x86_64"),
        ("peppermint_devuan-amd64.iso", "peppermint-os", "devuan", "amd64"),
        ("Fatdog64-904.iso", "fatdog64", "live", "x86_64"),
        ("slax-64bit-15.0.1.iso", "slax", "debian", "x86_64"),
        ("slax-32bit-slackware-15.0.4.iso", "slax", "slackware", "i386"),
        ("openmediavault_8.3.1-amd64.iso", "openmediavault", "installer", "amd64"),
        ("archcraft-2026.08.01-x86_64.iso", "archcraft", "main", "x86_64"),
        ("rescatux-0.74.iso", "rescatux", "repair", "multiarch"),
        ("Rhino-Linux-2026.1-amd64.iso", "rhino-linux", "unicorn", "amd64"),
        ("Rhino-Linux-2026.1-arm64-lomiri.iso", "rhino-linux", "lomiri", "arm64"),
        ("Porteus-XFCE-v5.01-x86_64.iso", "porteus", "xfce", "x86_64"),
        ("drweb-livedisk-900-cd.iso", "drweb-livedisk", "rescue", "x86_64"),
        ("MidnightBSD-4.0.7--amd64-disc1.iso", "midnightbsd", "disc1", "amd64"),
        ("dfly-x86_64-6.4.2_REL.iso", "dragonflybsd", "installer", "x86_64"),
        (
            "archboot-2026.09.07-01.02-7.2.3-arch1-3-latest-x86_64.iso",
            "archboot",
            "rescue-installer",
            "x86_64",
        ),
        ("KNOPPIX_V9.1DVD-2021-01-25-EN.iso", "knoppix", "dvd", "multiarch"),
        (
            "mabox-linux-26.09-Istredd-260904-linux618.iso",
            "mabox-linux",
            "desktop",
            "x86_64",
        ),
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
        ("omnios-stable-r151058.iso", "omnios", "installer", "x86_64"),
        ("omnios-lts-r151054r.iso", "omnios", "installer", "x86_64"),
        ("omnios-bloody-20260823.iso", "omnios", "installer", "x86_64"),
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
        ("harvester-v1.8.2-amd64.iso", "harvester", "full", "amd64"),
        (
            "harvester-v1.8.2-amd64-net-install.iso",
            "harvester",
            "netinstall",
            "amd64",
        ),
        ("harvester-v1.8.2-arm64.iso", "harvester", "full", "arm64"),
        ("Solus-Budgie-Release-2026-04-18.iso", "solus", "budgie", "x86_64"),
        ("Solus-GNOME-Release-2026-04-18.iso", "solus", "gnome", "x86_64"),
        ("TrueNAS-SCALE-25.10.7.iso", "truenas", "community", "x86_64"),
        ("TrueNAS-26.0.0-BETA.3.iso", "truenas", "community", "x86_64"),
        ("TUXEDO-OS-202608031247.iso", "tuxedo-os", "desktop", "x86_64"),
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
        ("carbon-1-260211-amd64.hybrid.iso", "bunsenlabs", "desktop", "amd64"),
        ("securityonion-3.2.0-20260729.iso", "security-onion", "installer", "x86_64"),
        ("metal-amd64.iso", "talos-linux", "metal", "amd64"),
        ("metal-arm64.iso", "talos-linux", "metal", "arm64"),
        ("antiX-26_x64-full.iso", "antix", "full", "x86_64"),
        ("antiX-23.2_386-core.iso", "antix", "core", "386"),
        ("antiX-23.2-net_x64-net.iso", "antix", "net", "x86_64"),
        ("MX-25.2_Xfce_x64.iso", "mx-linux", "xfce", "x86_64"),
        ("MX-25.2_Xfce_ahs_x64.iso", "mx-linux", "xfce", "x86_64"),
        ("MX-25.2_KDE_x64.iso", "mx-linux", "kde", "x86_64"),
        ("MX-25.2_fluxbox_x64.iso", "mx-linux", "fluxbox", "x86_64"),
        ("caine14.0.iso", "caine", "forensics-live", "x86_64"),
        ("kaisenlinuxrolling3.0-amd64-KDE.iso", "kaisen-linux", "kde", "amd64"),
        (
            "kaisenlinuxrolling3.0-amd64-SR.iso",
            "kaisen-linux",
            "system-rescue",
            "amd64",
        ),
        ("kaisenlinuxrolling3.0-amd64-NETINST.iso", "kaisen-linux", "netinst", "amd64"),
        (
            "casuarina-linux-x86_64-LIVE-20260518-base.iso",
            "casuarina-linux",
            "base",
            "x86_64",
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


def test_blackarch_detection_preserves_rolling_channel_without_enabling_downloads() -> None:
    provider = provider_map()["blackarch"]

    detected = provider.detect(Path("blackarch-linux-slim-2026.09.01-x86_64.iso"))

    assert detected is not None
    assert detected.identity.channel == "rolling"
    assert provider.supports_automatic_download is False


def test_drweb_livedisk_is_detection_only_without_strong_publisher_checksum() -> None:
    provider = provider_map()["drweb-livedisk"]

    detected = provider.detect(Path("drweb-livedisk-900-cd.iso"))

    assert detected is not None
    assert provider.supports_automatic_download is False


def test_dragonflybsd_is_detection_only_without_strong_publisher_checksum() -> None:
    provider = provider_map()["dragonflybsd"]

    detected = provider.detect(Path("dfly-x86_64-6.4.2_REL.iso"))

    assert detected is not None
    assert provider.supports_automatic_download is False


@pytest.mark.parametrize("provider_id", ["archboot", "knoppix", "mabox-linux"])
def test_additional_media_without_sha2_are_detection_only(provider_id: str) -> None:
    assert provider_map()[provider_id].supports_automatic_download is False


def test_unknown_filename_is_not_guessed() -> None:
    assert identify_iso(Path("renamed.iso")).identity is None


def test_artix_weekly_filename_is_not_silently_assigned_to_stable() -> None:
    assert identify_iso(Path("artix-base-openrc-20260903-x86_64.iso")).identity is None


def test_omnios_ambiguous_unlabelled_channel_is_not_guessed() -> None:
    assert identify_iso(Path("omnios-r151056.iso")).identity is None
    assert identify_iso(Path("TUXEDO-OS_current.iso")).identity is None


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
