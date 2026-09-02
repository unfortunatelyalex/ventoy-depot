from __future__ import annotations

import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .models import Distro, Release


class CatalogError(RuntimeError):
    """Official release metadata could not be determined safely."""


@dataclass(frozen=True)
class Catalog:
    """Official release metadata endpoints."""

    timeout: float = 30.0

    def resolve(self, distro: Distro, architecture: str = "amd64") -> Release:
        if distro == Distro.ARCH:
            return self._arch()
        if distro == Distro.UBUNTU:
            return self._ubuntu(architecture)
        if distro == Distro.DEBIAN:
            return self._debian(architecture)
        if distro == Distro.FEDORA:
            return self._fedora(architecture)
        raise CatalogError(
            f"Automatic resolution for {distro.value} needs an official source mapping. "
            "Use the interactive source mapping rather than downloading from an unverified URL."
        )

    def _arch(self) -> Release:
        base = "https://geo.mirror.pkgbuild.com/iso/latest/"
        sums = self._get(base + "sha256sums.txt").decode("utf-8")
        match = re.search(r"^([a-fA-F0-9]{64})\s+\*?(archlinux-x86_64\.iso)$", sums, re.M)
        if not match:
            raise CatalogError(
                "The official Arch checksum list did not contain archlinux-x86_64.iso."
            )
        version_match = re.search(r"archlinux-(\d{4}\.\d{2}\.\d{2})", sums)
        version = version_match.group(1) if version_match else "latest"
        return Release(
            Distro.ARCH,
            version,
            "x86_64",
            base + match.group(2),
            base + "sha256sums.txt",
            match.group(2),
            base + "sha256sums.txt.sig",
        )

    def _ubuntu(self, architecture: str) -> Release:
        index = self._get("https://releases.ubuntu.com/").decode("utf-8")
        releases = re.findall(r'href="(\d+\.\d+(?:\.\d+)?)/"', index)
        if not releases:
            raise CatalogError("Could not find Ubuntu releases on the official release server.")
        version = max(releases, key=_version_key)
        base = f"https://releases.ubuntu.com/{version}/"
        filename = self._filename_from_checksums(
            base + "SHA256SUMS",
            rf"(ubuntu-{re.escape(version)}(?:\.\d+)?-desktop-{re.escape(architecture)}\.iso)",
        )
        return Release(
            Distro.UBUNTU, version, architecture, base + filename, base + "SHA256SUMS", filename
        )

    def _debian(self, architecture: str) -> Release:
        if architecture not in {"amd64", "arm64"}:
            raise CatalogError(f"Debian does not have a configured ISO feed for {architecture}.")
        base = f"https://cdimage.debian.org/debian-cd/current/{architecture}/iso-cd/"
        filename = self._filename_from_checksums(
            base + "SHA512SUMS", rf"(debian-[\d.]+-{re.escape(architecture)}-netinst\.iso)"
        )
        version = re.search(r"debian-([\d.]+)-", filename)
        if not version:
            raise CatalogError("Could not read the Debian version from the official filename.")
        return Release(
            Distro.DEBIAN,
            version.group(1),
            architecture,
            base + filename,
            base + "SHA512SUMS",
            filename,
            checksum_algorithm="sha512",
        )

    def _fedora(self, architecture: str) -> Release:
        if architecture not in {"x86_64", "aarch64"}:
            raise CatalogError(f"Fedora does not have a configured ISO feed for {architecture}.")
        release_root = "https://dl.fedoraproject.org/pub/fedora/linux/releases/"
        index = self._get(release_root).decode("utf-8")
        versions = re.findall(r'href="(\d+)/"', index)
        if not versions:
            raise CatalogError("Could not find Fedora releases on the official release server.")
        version = str(max(int(item) for item in versions))
        base = f"{release_root}{version}/Workstation/{architecture}/iso/"
        listing = self._get(base).decode("utf-8")
        iso_match = re.search(
            rf'href="(Fedora-Workstation-Live-{re.escape(architecture)}-{version}-[^"]+\.iso)"',
            listing,
        )
        checksum_match = re.search(r'href="([^"]*CHECKSUM)"', listing)
        if not iso_match or not checksum_match:
            raise CatalogError(
                "The official Fedora directory did not contain an ISO and checksum file."
            )
        filename = iso_match.group(1)
        return Release(
            Distro.FEDORA,
            version,
            architecture,
            base + filename,
            base + checksum_match.group(1),
            filename,
        )

    def _filename_from_checksums(self, checksum_url: str, filename_pattern: str) -> str:
        text = self._get(checksum_url).decode("utf-8")
        match = re.search(rf"^[a-fA-F0-9]+\s+\*?{filename_pattern}$", text, re.M)
        if not match:
            raise CatalogError("The official checksum list did not contain a matching ISO.")
        return match.group(1)

    def _get(self, url: str) -> bytes:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise CatalogError("Only HTTPS official release metadata is allowed.")
        request = urllib.request.Request(url, headers={"User-Agent": "ventoy-iso-updater/0.1"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))
