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

    def detect(self, path: Path) -> DetectedIso | None:
        for rule in self.rules:
            if match := rule.expression.search(path.name):
                values = match.groupdict()
                architecture = _architecture(
                    values.get("architecture") or rule.default_architecture
                )
                identity = IsoIdentity(
                    provider_id=self.provider_id,
                    product_id=rule.product_id,
                    edition=_lower(values.get("edition")),
                    flavor=_lower(values.get("flavor")),
                    channel=_lower(values.get("channel")) or rule.default_channel,
                    architecture=architecture,
                    language=_lower(values.get("language")),
                    version=values.get("version"),
                    build=values.get("build"),
                )
                return DetectedIso(path, identity, 0.98, "filename")
        return None

    def resolve(self, identity: IsoIdentity) -> ReleaseArtifact:
        raise ProviderError(
            f"{self.display_name} release resolution is not available offline; "
            "refresh official provider metadata first."
        )


def _lower(value: str | None) -> str | None:
    return value.lower() if value else None


def _architecture(value: str) -> str:
    return {"64bit": "amd64", "64-bit": "amd64", "x64": "x86_64"}.get(value.lower(), value.lower())


COMMON = ProviderCapabilities((), ("amd64", "x86_64", "arm64", "aarch64"), (), ("stable",))

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
        COMMON,
    ),
    FilenameProvider(
        "ubuntu",
        "Ubuntu",
        (
            FilenameRule(
                re.compile(
                    r"ubuntu-(?P<version>\d+\.\d+(?:\.\d+)?)-(?P<edition>desktop|live-server)-(?P<architecture>amd64|arm64)\.iso$",
                    re.I,
                ),
                "ubuntu",
                "lts",
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
                    r"debian-live-(?P<version>\d+(?:\.\d+){0,2})-(?P<architecture>amd64|arm64)-(?P<edition>[^.]+)\.iso$",
                    re.I,
                ),
                "debian-live",
            ),
        ),
        ProviderCapabilities(("netinst", "dvd", "live"), ("amd64", "arm64"), (), ("stable",)),
    ),
    FilenameProvider(
        "fedora",
        "Fedora",
        (
            FilenameRule(
                re.compile(
                    r"Fedora-(?P<edition>Workstation|Server|KDE|Silverblue|IoT)(?:-Live)?-(?P<architecture>x86_64|aarch64)-(?P<version>\d+)(?:-(?P<build>[\d.]+))?\.iso$",
                    re.I,
                ),
                "fedora",
            ),
        ),
        ProviderCapabilities(
            ("workstation", "server", "kde", "silverblue", "iot"),
            ("x86_64", "aarch64"),
            (),
            ("stable",),
        ),
    ),
    FilenameProvider(
        "linux-mint",
        "Linux Mint",
        (
            FilenameRule(
                re.compile(
                    r"linuxmint-(?P<version>\d+(?:\.\d+){0,2})-(?P<edition>cinnamon|mate|xfce)(?:-(?P<architecture>64bit|amd64))?\.iso$",
                    re.I,
                ),
                "linux-mint",
                default_architecture="amd64",
            ),
        ),
        ProviderCapabilities(("cinnamon", "mate", "xfce"), ("amd64",), (), ("stable",)),
    ),
    FilenameProvider(
        "endeavouros",
        "EndeavourOS",
        (
            FilenameRule(
                re.compile(r"EndeavourOS_(?P<version>[A-Za-z0-9_.-]+)\.iso$", re.I),
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
                    r"cachyos-(?P<edition>desktop|handheld)-(?P<version>[\d.]+)(?:-(?P<architecture>x86_64))?\.iso$",
                    re.I,
                ),
                "cachyos",
                default_architecture="x86_64",
            ),
        ),
        ProviderCapabilities(("desktop", "handheld"), ("x86_64",), (), ("stable",)),
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
                    r"manjaro-(?P<edition>[a-z0-9-]+)-(?P<version>[\d.]+)-(?P<flavor>minimal|full)-(?P<architecture>x86_64|aarch64)\.iso$",
                    re.I,
                ),
                "manjaro",
            ),
        ),
        ProviderCapabilities((), ("x86_64", "aarch64"), (), ("stable", "review", "preview")),
    ),
    FilenameProvider(
        "pop-os",
        "Pop!_OS",
        (
            FilenameRule(
                re.compile(
                    r"pop-os_(?P<version>[\d.]+)_(?P<architecture>amd64|arm64)_(?P<edition>nvidia|intel|generic)(?:_(?P<build>\d+))?\.iso$",
                    re.I,
                ),
                "pop-os",
            ),
        ),
        ProviderCapabilities(("generic", "intel", "nvidia"), ("amd64", "arm64"), (), ("stable",)),
    ),
    FilenameProvider(
        "nobara",
        "Nobara",
        (
            FilenameRule(
                re.compile(
                    r"Nobara-(?P<version>\d+)-(?P<edition>Official|GNOME|KDE|Steam-HTPC|Steam-Handheld)-(?P<architecture>x86_64)\.iso$",
                    re.I,
                ),
                "nobara",
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
        "vanilla-os",
        "Vanilla OS",
        (
            FilenameRule(
                re.compile(
                    r"VanillaOS-(?P<version>[\d.]+)(?:-(?P<architecture>amd64))?\.iso$",
                    re.I,
                ),
                "vanilla-os",
                default_architecture="amd64",
            ),
        ),
        ProviderCapabilities((), ("amd64",), (), ("stable",)),
    ),
    FilenameProvider(
        "zorin-os",
        "Zorin OS",
        (
            FilenameRule(
                re.compile(
                    r"Zorin-OS-(?P<version>[\d.]+)-(?P<edition>Core|Education|Lite|Pro)-(?P<architecture>64-bit|amd64)\.iso$",
                    re.I,
                ),
                "zorin-os",
            ),
        ),
        ProviderCapabilities(("core", "education", "lite"), ("amd64",), (), ("stable",)),
    ),
)
