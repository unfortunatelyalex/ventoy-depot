from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..models import DetectedIso, IsoIdentity, ReleaseArtifact
from .base import Provider, ProviderCapabilities, ProviderError


@dataclass(frozen=True)
class FilenameRule:
    expression: re.Pattern[str]
    product_id: str
    default_channel: str = "stable"
    default_architecture: str = "unknown"
    default_edition: str | None = None
    default_flavor: str | None = None
    default_language: str | None = None


class FilenameProvider(Provider):
    """Variant-preserving filename detector; resolution is supplied by a driver later."""

    def __init__(
        self,
        provider_id: str,
        display_name: str,
        rules: tuple[FilenameRule, ...],
        capabilities: ProviderCapabilities,
    ) -> None:
        self.provider_id = provider_id
        self.display_name = display_name
        self.rules = rules
        self.capabilities = capabilities

    @property
    def products(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(rule.product_id for rule in self.rules))

    def detect(self, path: Path) -> DetectedIso | None:
        for rule in self.rules:
            if match := rule.expression.fullmatch(path.name):
                values = match.groupdict()
                architecture = _architecture(
                    values.get("architecture") or rule.default_architecture
                )
                identity = IsoIdentity(
                    provider_id=self.provider_id,
                    product_id=rule.product_id,
                    edition=_lower(values.get("edition") or rule.default_edition),
                    flavor=_lower(values.get("flavor") or rule.default_flavor),
                    channel=_lower(values.get("channel")) or rule.default_channel,
                    architecture=architecture,
                    language=_lower(values.get("language") or rule.default_language),
                    version=values.get("version"),
                    build=values.get("build"),
                )
                return DetectedIso(path, identity, 0.98, "filename")
        return None

    def resolve(self, identity: IsoIdentity) -> ReleaseArtifact:
        from .resolvers import resolve_release

        if identity.provider_id != self.provider_id:
            raise ProviderError("Provider identity does not match the selected provider.")
        products = {rule.product_id for rule in self.rules}
        if identity.product_id not in products:
            raise ProviderError("Product identity is not supported by the selected provider.")
        self._validate_dimension("edition", identity.edition, self.capabilities.editions)
        self._validate_dimension("flavor", identity.flavor, self.capabilities.flavors)
        self._validate_dimension(
            "architecture", identity.architecture, self.capabilities.architectures
        )
        self._validate_dimension("language", identity.language, self.capabilities.languages)
        self._validate_dimension("channel", identity.channel, self.capabilities.channels)
        return resolve_release(self.provider_id, identity)

    @staticmethod
    def _validate_dimension(name: str, value: str | None, supported: tuple[str, ...]) -> None:
        normalized = {item.lower() for item in supported}
        if value is not None and value.lower() not in normalized:
            raise ProviderError(f"Unsupported {name} for this provider: {value}")

    def is_newer(self, artifact: ReleaseArtifact, identity: IsoIdentity) -> bool:
        if (
            self.provider_id == "vanilla-os"
            and identity.version
            and identity.version.startswith("22.")
        ):
            return True
        if artifact.version == identity.version and artifact.build and identity.build:
            from ..models import is_newer_version

            return is_newer_version(artifact.build, identity.build)
        return super().is_newer(artifact, identity)


def _lower(value: str | None) -> str | None:
    return value.lower() if value else None


def _architecture(value: str) -> str:
    return {
        "64bit": "x86_64",
        "64-bit": "x86_64",
        "x64": "x86_64",
        "x86-64": "x86_64",
        "all": "amd64",
    }.get(value.lower(), value.lower())


BUILTIN_PROVIDERS: tuple[Provider, ...] = (
    FilenameProvider(
        "arch",
        "Arch Linux",
        (
            FilenameRule(
                re.compile(
                    r"archlinux-(?P<version>\d{4}\.\d{2}\.\d{2})-(?P<architecture>x86_64)\.iso$",
                    re.I,
                ),
                "archlinux",
            ),
        ),
        ProviderCapabilities((), ("x86_64",), (), ("stable",)),
    ),
    FilenameProvider(
        "alpine",
        "Alpine Linux",
        (
            FilenameRule(
                re.compile(
                    r"alpine-(?P<edition>standard|extended|virtual|xen)-"
                    r"(?P<version>\d+(?:\.\d+)+)-"
                    r"(?P<architecture>x86|x86_64|aarch64|armv7|loongarch64|ppc64le|riscv64|s390x)\.iso$",
                    re.I,
                ),
                "alpine-linux",
            ),
        ),
        ProviderCapabilities(
            ("standard", "extended", "virtual", "xen"),
            ("x86", "x86_64", "aarch64", "armv7", "loongarch64", "ppc64le", "riscv64", "s390x"),
            (),
            ("stable",),
        ),
    ),
    FilenameProvider(
        "rocky-linux",
        "Rocky Linux",
        (
            FilenameRule(
                re.compile(
                    r"Rocky-(?P<version>(?P<channel>8|9|10)\.\d+)-"
                    r"(?P<architecture>x86_64|aarch64)-(?P<edition>boot|dvd|dvd1|minimal)\.iso$",
                    re.I,
                ),
                "rocky-linux",
            ),
            FilenameRule(
                re.compile(
                    r"Rocky-(?P<channel>8|9|10)-latest-"
                    r"(?P<architecture>x86_64|aarch64)-(?P<edition>boot|dvd|dvd1|minimal)\.iso$",
                    re.I,
                ),
                "rocky-linux",
                default_flavor="latest-alias",
            ),
        ),
        ProviderCapabilities(
            ("boot", "dvd", "dvd1", "minimal"),
            ("x86_64", "aarch64"),
            (),
            ("8", "9", "10"),
            ("latest-alias",),
        ),
    ),
    FilenameProvider(
        "almalinux",
        "AlmaLinux OS",
        (
            FilenameRule(
                re.compile(
                    r"AlmaLinux-(?P<version>(?P<channel>8|9|10)\.\d+)-"
                    r"(?P<architecture>x86_64|x86_64_v2|aarch64|ppc64le|s390x)-"
                    r"(?P<edition>boot|dvd|minimal)\.iso$",
                    re.I,
                ),
                "almalinux",
            ),
            FilenameRule(
                re.compile(
                    r"AlmaLinux-(?P<channel>8|9|10)-latest-"
                    r"(?P<architecture>x86_64|x86_64_v2|aarch64|ppc64le|s390x)-"
                    r"(?P<edition>boot|dvd|minimal)\.iso$",
                    re.I,
                ),
                "almalinux",
                default_flavor="latest-alias",
            ),
        ),
        ProviderCapabilities(
            ("boot", "dvd", "minimal"),
            ("x86_64", "x86_64_v2", "aarch64", "ppc64le", "s390x"),
            (),
            ("8", "9", "10"),
            ("latest-alias",),
        ),
    ),
    FilenameProvider(
        "ubuntu",
        "Ubuntu",
        (
            FilenameRule(
                re.compile(
                    r"ubuntu-(?P<version>(?:2[02468]|[02468]\d)\.04(?:\.\d+)?)-(?P<edition>desktop|live-server)-(?P<architecture>amd64|arm64)\.iso$",
                    re.I,
                ),
                "ubuntu",
                "lts",
            ),
            FilenameRule(
                re.compile(
                    r"ubuntu-(?P<version>\d{2}\.(?!04(?:\.|-))\d{2}(?:\.\d+)?)-(?P<edition>desktop|live-server)-(?P<architecture>amd64|arm64)\.iso$",
                    re.I,
                ),
                "ubuntu",
                "interim",
            ),
        ),
        ProviderCapabilities(
            ("desktop", "live-server"), ("amd64", "arm64"), (), ("lts", "interim")
        ),
    ),
    FilenameProvider(
        "debian",
        "Debian",
        (
            FilenameRule(
                re.compile(
                    r"debian-(?P<version>\d+(?:\.\d+){0,2})-(?P<architecture>amd64|arm64)-(?P<edition>netinst|DVD-\d+)\.iso$",
                    re.I,
                ),
                "debian",
            ),
            FilenameRule(
                re.compile(
                    r"debian-live-(?P<version>\d+(?:\.\d+){1,2})-(?P<architecture>amd64)-(?P<flavor>cinnamon|gnome|kde|lxde|lxqt|mate|standard|xfce)\.iso$",
                    re.I,
                ),
                "debian",
                default_edition="live",
            ),
        ),
        ProviderCapabilities(
            ("netinst", "dvd-1", "dvd-2", "dvd-3", "live"),
            ("amd64", "arm64"),
            (),
            ("stable",),
            ("cinnamon", "gnome", "kde", "lxde", "lxqt", "mate", "standard", "xfce"),
        ),
    ),
    FilenameProvider(
        "fedora",
        "Fedora",
        (
            FilenameRule(
                re.compile(
                    r"Fedora-(?P<edition>Workstation|KDE)(?:-Desktop)?-(?P<flavor>Live)-(?P<architecture>x86_64|aarch64)-(?P<version>\d+)-(?P<build>\d+(?:\.\d+)+)\.iso$",
                    re.I,
                ),
                "fedora",
            ),
            FilenameRule(
                re.compile(
                    r"Fedora-(?P<edition>Workstation|KDE-Desktop|Budgie|COSMIC|Cinnamon|"
                    r"KDE-Mobile|LXDE|LXQt|MATE_Compiz|MiracleWM|SoaS|Sway|Xfce|i3)-"
                    r"(?P<flavor>Live)-(?P<version>\d+)-(?P<build>\d+(?:\.\d+)+)\."
                    r"(?P<architecture>x86_64|aarch64)\.iso$",
                    re.I,
                ),
                "fedora",
            ),
            FilenameRule(
                re.compile(
                    r"Fedora-(?P<edition>Server)-(?P<flavor>dvd)-(?P<architecture>x86_64|aarch64)-(?P<version>\d+)-(?P<build>\d+(?:\.\d+)+)\.iso$",
                    re.I,
                ),
                "fedora",
            ),
            FilenameRule(
                re.compile(
                    r"Fedora-(?P<edition>Silverblue)-(?P<flavor>ostree)-(?P<architecture>x86_64|aarch64)-(?P<version>\d+)-(?P<build>\d+(?:\.\d+)+)\.iso$",
                    re.I,
                ),
                "fedora",
            ),
        ),
        ProviderCapabilities(
            (
                "workstation",
                "server",
                "kde",
                "kde-desktop",
                "silverblue",
                "budgie",
                "cosmic",
                "cinnamon",
                "kde-mobile",
                "lxde",
                "lxqt",
                "mate_compiz",
                "miraclewm",
                "soas",
                "sway",
                "xfce",
                "i3",
            ),
            ("x86_64", "aarch64"),
            (),
            ("stable",),
            ("live", "dvd", "ostree"),
        ),
    ),
    FilenameProvider(
        "linux-mint",
        "Linux Mint",
        (
            FilenameRule(
                re.compile(
                    r"linuxmint-(?P<version>\d+(?:\.\d+){1,2})-(?P<edition>cinnamon|mate|xfce)-(?:64bit|amd64)(?:-(?P<flavor>edge))?\.iso$",
                    re.I,
                ),
                "linux-mint",
                default_architecture="x86_64",
            ),
        ),
        ProviderCapabilities(("cinnamon", "mate", "xfce"), ("x86_64",), (), ("stable",)),
    ),
    FilenameProvider(
        "endeavouros",
        "EndeavourOS",
        (
            FilenameRule(
                re.compile(
                    r"EndeavourOS_(?P<build>[A-Za-z0-9-]+)-(?P<version>\d{4}\.\d{2}\.\d{2})\.iso$",
                    re.I,
                ),
                "endeavouros",
                default_architecture="x86_64",
            ),
        ),
        ProviderCapabilities((), ("x86_64",), (), ("stable",)),
    ),
    FilenameProvider(
        "cachyos",
        "CachyOS",
        (
            FilenameRule(
                re.compile(
                    r"cachyos-(?P<edition>desktop|handheld)-linux-(?P<version>\d{6})\.iso$",
                    re.I,
                ),
                "cachyos",
                default_architecture="x86_64",
            ),
            FilenameRule(
                re.compile(r"cachyos-(?P<edition>kde)-linux-(?P<version>\d{6})\.iso$", re.I),
                "cachyos",
                default_architecture="x86_64",
            ),
        ),
        ProviderCapabilities(("desktop", "handheld", "kde"), ("x86_64",), (), ("stable",)),
    ),
    FilenameProvider(
        "clonezilla",
        "Clonezilla Live",
        (
            FilenameRule(
                re.compile(
                    r"clonezilla-live-(?P<version>\d+(?:\.\d+)+-\d+)-amd64\.iso$",
                    re.I,
                ),
                "clonezilla-live",
                default_architecture="amd64",
                default_edition="debian",
            ),
            FilenameRule(
                re.compile(r"clonezilla-live-(?P<version>\d{8}-[a-z]+)-amd64\.iso$", re.I),
                "clonezilla-live",
                default_architecture="amd64",
                default_edition="ubuntu",
            ),
        ),
        ProviderCapabilities(("debian", "ubuntu"), ("amd64",), (), ("stable",)),
    ),
    FilenameProvider(
        "omarchy",
        "Omarchy",
        (
            FilenameRule(
                re.compile(
                    r"omarchy-(?P<version>[\d.]+)(?:-(?P<architecture>x86_64))?\.iso$",
                    re.I,
                ),
                "omarchy",
                default_architecture="x86_64",
            ),
        ),
        ProviderCapabilities((), ("x86_64",), (), ("stable",)),
    ),
    FilenameProvider(
        "manjaro",
        "Manjaro",
        (
            FilenameRule(
                re.compile(
                    r"manjaro-(?P<edition>gnome|kde|xfce)-(?P<version>\d+(?:\.\d+)+-rc\d+)-(?P<flavor>minimal)-(?P<build>\d{6})-linux\d+\.iso$",
                    re.I,
                ),
                "manjaro",
                "review",
                default_architecture="x86_64",
            ),
            FilenameRule(
                re.compile(
                    r"manjaro-(?P<edition>gnome|kde|xfce)-(?P<version>\d+(?:\.\d+)+-rc\d+)-(?P<build>\d{6})-linux\d+\.iso$",
                    re.I,
                ),
                "manjaro",
                "review",
                default_architecture="x86_64",
                default_flavor="full",
            ),
            FilenameRule(
                re.compile(
                    r"manjaro-(?P<edition>gnome|kde|xfce)-(?P<version>\d+(?:\.\d+)+)-(?P<flavor>minimal)-(?P<build>\d{6})-linux\d+\.iso$",
                    re.I,
                ),
                "manjaro",
                default_architecture="x86_64",
            ),
            FilenameRule(
                re.compile(
                    r"manjaro-(?P<edition>gnome|kde|xfce)-(?P<version>\d+(?:\.\d+)+)-(?P<build>\d{6})-linux\d+\.iso$",
                    re.I,
                ),
                "manjaro",
                default_architecture="x86_64",
                default_flavor="full",
            ),
        ),
        ProviderCapabilities(
            ("gnome", "kde", "xfce"),
            ("x86_64",),
            (),
            ("stable", "review", "preview"),
            ("full", "minimal"),
        ),
    ),
    FilenameProvider(
        "pop-os",
        "Pop!_OS",
        (
            FilenameRule(
                re.compile(
                    r"pop-os_(?P<version>\d{2}\.\d{2})_(?P<architecture>amd64|arm64)_(?P<edition>nvidia|generic)_(?P<build>\d+)\.iso$",
                    re.I,
                ),
                "pop-os",
            ),
        ),
        ProviderCapabilities(("generic", "nvidia"), ("amd64", "arm64"), (), ("stable",)),
    ),
    FilenameProvider(
        "nobara",
        "Nobara",
        (
            FilenameRule(
                re.compile(
                    r"Nobara-(?P<version>\d+)-(?P<edition>Official|GNOME|KDE|Steam-HTPC|Steam-Handheld)-(?P<build>\d{4}-\d{2}-\d{2})\.iso$",
                    re.I,
                ),
                "nobara",
                default_architecture="x86_64",
            ),
            FilenameRule(
                re.compile(
                    r"Nobara-(?P<version>\d+)-(?P<edition>Official|GNOME|KDE|Steam-HTPC|Steam-Handheld)-(?P<architecture>x86_64)\.iso$",
                    re.I,
                ),
                "nobara",
            ),
            FilenameRule(
                re.compile(
                    r"Nobara-(?P<version>\d+)-(?P<edition>Official|GNOME|KDE|Steam-HTPC|Steam-Handheld)-(?P<flavor>Nvidia)-(?P<build>\d{4}-\d{2}-\d{2})\.iso$",
                    re.I,
                ),
                "nobara",
                default_architecture="x86_64",
            ),
        ),
        ProviderCapabilities(
            ("official", "gnome", "kde", "steam-htpc", "steam-handheld"),
            ("x86_64",),
            (),
            ("stable",),
        ),
    ),
    FilenameProvider(
        "gparted-live",
        "GParted Live",
        (
            FilenameRule(
                re.compile(
                    r"gparted-live-(?P<version>\d+(?:\.\d+)+-\d+)-(?P<architecture>amd64)\.iso$",
                    re.I,
                ),
                "gparted-live",
                default_edition="live",
            ),
        ),
        ProviderCapabilities(("live",), ("amd64",), (), ("stable",)),
    ),
    FilenameProvider(
        "kali-linux",
        "Kali Linux",
        (
            FilenameRule(
                re.compile(
                    r"kali-linux-(?P<version>\d{4}\.\d+)-(?P<edition>installer|installer-netinst|installer-purple|live|live-everything)-(?P<architecture>amd64|arm64)\.iso$",
                    re.I,
                ),
                "kali-linux",
            ),
        ),
        ProviderCapabilities(
            ("installer", "installer-netinst", "installer-purple", "live", "live-everything"),
            ("amd64", "arm64"),
            (),
            ("stable",),
        ),
    ),
    FilenameProvider(
        "nixos",
        "NixOS",
        (
            FilenameRule(
                re.compile(
                    r"nixos-(?P<flavor>plasma5)-(?P<version>\d+\.\d+\.\d+\.[a-f0-9]+)-(?P<architecture>x86_64|aarch64)-linux\.iso$",
                    re.I,
                ),
                "nixos",
                default_edition="graphical",
            ),
            FilenameRule(
                re.compile(
                    r"nixos-(?P<edition>graphical|minimal)-(?P<version>\d+\.\d+\.\d+\.[a-f0-9]+)-(?P<architecture>x86_64|aarch64)-linux\.iso$",
                    re.I,
                ),
                "nixos",
            ),
        ),
        ProviderCapabilities(
            ("graphical", "minimal"),
            ("x86_64", "aarch64"),
            (),
            ("stable",),
            ("plasma5",),
        ),
    ),
    FilenameProvider(
        "systemrescue",
        "SystemRescue",
        (
            FilenameRule(
                re.compile(r"systemrescue-(?P<version>\d+(?:\.\d+)+)-amd64\.iso$", re.I),
                "systemrescue",
                default_architecture="amd64",
                default_edition="live",
            ),
        ),
        ProviderCapabilities(("live",), ("amd64",), (), ("stable",)),
    ),
    FilenameProvider(
        "opensuse-tumbleweed",
        "openSUSE Tumbleweed",
        (
            FilenameRule(
                re.compile(
                    r"openSUSE-Tumbleweed-(?P<edition>DVD|NET|Rescue-CD|GNOME-Live|KDE-Live|XFCE-Live)-"
                    r"(?P<architecture>x86_64|aarch64)-Snapshot(?P<version>\d{8})-Media\.iso$",
                    re.I,
                ),
                "opensuse-tumbleweed",
                default_channel="rolling",
            ),
            FilenameRule(
                re.compile(
                    r"openSUSE-Tumbleweed-(?P<edition>DVD|NET|Rescue-CD|GNOME-Live|KDE-Live|XFCE-Live)-"
                    r"(?P<architecture>x86_64|aarch64)-(?P<version>Current)\.iso$",
                    re.I,
                ),
                "opensuse-tumbleweed",
                default_channel="rolling",
            ),
        ),
        ProviderCapabilities(
            ("dvd", "net", "rescue-cd", "gnome-live", "kde-live", "xfce-live"),
            ("x86_64", "aarch64"),
            (),
            ("rolling",),
        ),
    ),
    FilenameProvider(
        "freebsd",
        "FreeBSD",
        (
            FilenameRule(
                re.compile(
                    r"FreeBSD-(?P<version>\d+(?:\.\d+)+)-RELEASE-"
                    r"(?P<architecture>amd64|arm64)-(?P<edition>disc1|dvd1|bootonly)\.iso$",
                    re.I,
                ),
                "freebsd",
                default_channel="release",
            ),
        ),
        ProviderCapabilities(
            ("disc1", "dvd1", "bootonly"),
            ("amd64", "arm64"),
            (),
            ("release",),
        ),
    ),
    FilenameProvider(
        "grml",
        "Grml",
        (
            FilenameRule(
                re.compile(
                    r"grml-(?P<edition>full|small)-(?P<version>\d{4}\.\d{2})-"
                    r"(?P<architecture>amd64|arm64)\.iso$",
                    re.I,
                ),
                "grml",
            ),
        ),
        ProviderCapabilities(("full", "small"), ("amd64", "arm64"), (), ("stable",)),
    ),
    FilenameProvider(
        "qubes-os",
        "Qubes OS",
        (
            FilenameRule(
                re.compile(r"Qubes-R(?P<version>\d+(?:\.\d+)+)-x86_64\.iso$", re.I),
                "qubes-os",
                default_architecture="x86_64",
                default_edition="installer",
            ),
        ),
        ProviderCapabilities(("installer",), ("x86_64",), (), ("stable",)),
    ),
    FilenameProvider(
        "proxmox",
        "Proxmox",
        (
            FilenameRule(
                re.compile(
                    r"proxmox-ve_(?P<version>\d+(?:\.\d+)+-\d+)(?:-(?P<architecture>arm64))?\.iso$",
                    re.I,
                ),
                "proxmox-ve",
                default_architecture="amd64",
                default_edition="installer",
            ),
            FilenameRule(
                re.compile(r"proxmox-backup-server_(?P<version>\d+(?:\.\d+)+-\d+)\.iso$", re.I),
                "proxmox-backup-server",
                default_architecture="amd64",
                default_edition="installer",
            ),
            FilenameRule(
                re.compile(
                    r"proxmox-(?:mail-gateway|mailgateway)_(?P<version>\d+(?:\.\d+)+-\d+)\.iso$",
                    re.I,
                ),
                "proxmox-mail-gateway",
                default_architecture="amd64",
                default_edition="installer",
            ),
            FilenameRule(
                re.compile(
                    r"proxmox-datacenter-manager_(?P<version>\d+(?:\.\d+)+-\d+)\.iso$",
                    re.I,
                ),
                "proxmox-datacenter-manager",
                default_architecture="amd64",
                default_edition="installer",
            ),
        ),
        ProviderCapabilities(("installer",), ("amd64", "arm64"), (), ("stable",)),
    ),
    FilenameProvider(
        "rescuezilla",
        "Rescuezilla",
        (
            FilenameRule(
                re.compile(
                    r"rescuezilla-(?P<version>\d+(?:\.\d+)+)-64bit\.(?P<flavor>noble|oracular|questing|resolute)\.iso$",
                    re.I,
                ),
                "rescuezilla",
                default_architecture="amd64",
                default_edition="live",
            ),
        ),
        ProviderCapabilities(
            ("live",),
            ("amd64",),
            (),
            ("stable",),
            ("noble", "oracular", "questing", "resolute"),
        ),
    ),
    FilenameProvider(
        "tails",
        "Tails",
        (
            FilenameRule(
                re.compile(r"tails-amd64-(?P<version>\d+(?:\.\d+)+)\.iso$", re.I),
                "tails",
                default_architecture="amd64",
                default_edition="iso",
            ),
        ),
        ProviderCapabilities(("iso",), ("amd64",), (), ("stable",)),
    ),
    FilenameProvider(
        "memtest86-plus",
        "Memtest86+",
        (
            FilenameRule(
                re.compile(
                    r"mt86plus_(?P<version>\d+(?:\.\d+)+)_(?P<architecture>i586|x86_64)\.grub\.iso$",
                    re.I,
                ),
                "memtest86-plus",
                default_edition="grub",
            ),
            FilenameRule(
                re.compile(
                    r"mt86plus_(?P<version>\d+(?:\.\d+)+)_(?P<architecture>i586|x86_64)\.iso$",
                    re.I,
                ),
                "memtest86-plus",
                default_edition="bare",
            ),
            FilenameRule(
                re.compile(r"mt86plus_(?P<version>\d+(?:\.\d+)+)_LA64\.grub\.iso$", re.I),
                "memtest86-plus",
                default_architecture="loongarch64",
                default_edition="grub",
            ),
            FilenameRule(
                re.compile(r"mt86plus_(?P<version>\d+(?:\.\d+)+)_LA64\.iso$", re.I),
                "memtest86-plus",
                default_architecture="loongarch64",
                default_edition="bare",
            ),
        ),
        ProviderCapabilities(("grub", "bare"), ("i586", "x86_64", "loongarch64"), (), ("stable",)),
    ),
    FilenameProvider(
        "vanilla-os",
        "Vanilla OS",
        (
            FilenameRule(
                re.compile(
                    r"Vanilla-OS-(?P<version>\d+(?:\.\d+)*)-stable-(?P<architecture>amd64|arm64)\.(?P<build>\d{8})\.iso$",
                    re.I,
                ),
                "vanilla-os",
            ),
            FilenameRule(
                re.compile(
                    r"VanillaOS-(?P<version>22\.\d+)-all\.(?P<build>\d{8})\.iso$",
                    re.I,
                ),
                "vanilla-os",
                default_architecture="amd64",
            ),
            FilenameRule(
                re.compile(
                    r"VanillaOS-(?P<version>22\.\d+)(?:-(?P<architecture>amd64|all))?\.iso$",
                    re.I,
                ),
                "vanilla-os",
                default_architecture="amd64",
            ),
        ),
        ProviderCapabilities((), ("amd64", "arm64"), (), ("stable",)),
    ),
    FilenameProvider(
        "windows-11",
        "Windows 11",
        (
            FilenameRule(
                re.compile(r"Win11_(?P<version>\d{2}H\d)_German_x64\.iso$", re.I),
                "windows-11",
                default_architecture="x86_64",
                default_edition="multi-edition",
                default_flavor="consumer",
                default_language="de-de",
            ),
            FilenameRule(
                re.compile(r"Win11_(?P<version>\d{2}H\d)_English_x64\.iso$", re.I),
                "windows-11",
                default_architecture="x86_64",
                default_edition="multi-edition",
                default_flavor="consumer",
                default_language="en-us",
            ),
            FilenameRule(
                re.compile(r"Win11_(?P<version>\d{2}H\d)_EnglishInternational_x64\.iso$", re.I),
                "windows-11",
                default_architecture="x86_64",
                default_edition="multi-edition",
                default_flavor="consumer",
                default_language="en-gb",
            ),
        ),
        ProviderCapabilities(
            ("multi-edition",),
            ("x86_64",),
            ("de-de", "en-us", "en-gb"),
            ("stable",),
            ("consumer",),
        ),
    ),
    FilenameProvider(
        "zorin-os",
        "Zorin OS",
        (
            FilenameRule(
                re.compile(
                    r"Zorin-OS-(?P<version>\d+(?:\.\d+)+)-(?P<edition>Core|Education|Lite|Pro|Pro-Lite)-(?P<architecture>64-bit|amd64)(?:-r(?P<build>\d+))?\.iso$",
                    re.I,
                ),
                "zorin-os",
            ),
        ),
        ProviderCapabilities(
            ("core", "education", "lite", "pro", "pro-lite"),
            ("x86_64",),
            (),
            ("stable",),
        ),
    ),
    FilenameProvider(
        "netboot-xyz",
        "netboot.xyz",
        (
            FilenameRule(
                re.compile(r"netboot\.xyz\.iso$", re.I),
                "netboot-xyz",
                default_architecture="x86_64",
                default_edition="standard",
            ),
            FilenameRule(
                re.compile(r"netboot\.xyz-legacy\.iso$", re.I),
                "netboot-xyz",
                default_architecture="x86_64",
                default_edition="legacy",
            ),
            FilenameRule(
                re.compile(r"netboot\.xyz-arm64\.iso$", re.I),
                "netboot-xyz",
                default_architecture="arm64",
                default_edition="standard",
            ),
        ),
        ProviderCapabilities(("standard", "legacy"), ("x86_64", "arm64"), (), ("stable",)),
    ),
    FilenameProvider(
        "gentoo",
        "Gentoo Linux",
        (
            FilenameRule(
                re.compile(
                    r"install-(?P<architecture>amd64|arm64|x86)-minimal-"
                    r"(?P<version>\d{8}T\d{6}Z)\.iso$",
                    re.I,
                ),
                "gentoo",
                default_edition="minimal",
            ),
            FilenameRule(
                re.compile(r"livegui-amd64-(?P<version>\d{8}T\d{6}Z)\.iso$", re.I),
                "gentoo",
                default_architecture="amd64",
                default_edition="livegui",
            ),
        ),
        ProviderCapabilities(("minimal", "livegui"), ("amd64", "arm64", "x86"), (), ("stable",)),
    ),
    FilenameProvider(
        "hirens-bootcd-pe",
        "Hiren's BootCD PE",
        (
            FilenameRule(
                re.compile(r"HBCD_PE_x64\.iso$", re.I),
                "hirens-bootcd-pe",
                default_architecture="x86_64",
                default_edition="pe",
            ),
        ),
        ProviderCapabilities(("pe",), ("x86_64",), (), ("stable",)),
    ),
    FilenameProvider(
        "shredos",
        "ShredOS",
        (
            FilenameRule(
                re.compile(
                    r"shredos-(?P<version>\d{4}\.\d+_\d+)_"
                    r"(?P<architecture>x86-64|i686)_v"
                    r"(?P<build>\d+(?:\.\d+)+_\d{8})"
                    r"(?:_(?P<edition>lite))?"
                    r"(?:_(?P<flavor>plus-partition))?\.iso$",
                    re.I,
                ),
                "shredos",
                default_edition="standard",
            ),
        ),
        ProviderCapabilities(
            ("standard", "lite"),
            ("x86_64", "i686"),
            (),
            ("stable",),
            ("plus-partition",),
        ),
    ),
    FilenameProvider(
        "netbsd",
        "NetBSD",
        (
            FilenameRule(
                re.compile(
                    r"NetBSD-(?P<version>\d+(?:\.\d+)+)-"
                    r"(?P<architecture>amd64|i386)\.iso$",
                    re.I,
                ),
                "netbsd",
                default_edition="installer",
                default_channel="release",
            ),
        ),
        ProviderCapabilities(("installer",), ("amd64", "i386"), (), ("release",)),
    ),
)
