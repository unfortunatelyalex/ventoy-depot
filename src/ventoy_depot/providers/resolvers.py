from __future__ import annotations

import json
import re
from collections.abc import Iterable
from urllib.parse import urljoin

from ..models import IsoIdentity, ReleaseArtifact
from ..network import SafeHttpClient
from .base import ProviderError


def resolve_release(provider_id: str, identity: IsoIdentity) -> ReleaseArtifact:
    resolvers = {
        "arch": _arch,
        "ubuntu": _ubuntu,
        "debian": _debian,
        "fedora": _fedora,
        "linux-mint": _linux_mint,
        "endeavouros": _endeavouros,
        "omarchy": _omarchy,
        "manjaro": _manjaro,
        "pop-os": _pop_os,
        "vanilla-os": _vanilla_os,
        "zorin-os": _zorin_os,
    }
    try:
        resolver = resolvers[provider_id]
    except KeyError as error:
        raise ProviderError(
            f"Automatic updates for {provider_id} are not implemented yet."
        ) from error
    try:
        return resolver(identity)
    except ProviderError:
        raise
    except Exception as error:
        raise ProviderError(
            f"Could not read official {provider_id} release metadata: {error}"
        ) from error


def _artifact(
    version: str,
    filename: str,
    url: str,
    algorithm: str,
    checksum: str,
    hosts: Iterable[str],
    *,
    build: str | None = None,
    size_bytes: int | None = None,
) -> ReleaseArtifact:
    return ReleaseArtifact(
        version=version,
        build=build,
        filename=filename,
        download_url=url,
        size_bytes=size_bytes,
        checksum_algorithm=algorithm,
        checksum=checksum,
        signature_url=None,
        signer_fingerprints=(),
        allowed_hosts=frozenset(hosts),
    )


def _text(client: SafeHttpClient, url: str) -> str:
    return client.metadata(url).decode("utf-8", errors="replace")


def _checksum(text: str, filename: str, algorithm: str) -> str:
    length = 64 if algorithm == "sha256" else 128
    escaped = re.escape(filename)
    patterns = (
        rf"^(?P<hash>[A-Fa-f0-9]{{{length}}})\s+[* ]?{escaped}\s*$",
        rf"^{algorithm.upper()}\s*\({escaped}\)\s*=\s*(?P<hash>[A-Fa-f0-9]{{{length}}})\s*$",
    )
    for pattern in patterns:
        if match := re.search(pattern, text, re.MULTILINE):
            return match.group("hash").lower()
    stripped = text.strip()
    if re.fullmatch(rf"[A-Fa-f0-9]{{{length}}}(?:\s+.+)?", stripped):
        return stripped.split()[0].lower()
    raise ProviderError(f"Official checksum metadata does not contain {filename}.")


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(item) for item in re.findall(r"\d+", value))


def _arch(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.architecture != "x86_64":
        raise ProviderError("Arch Linux automatic updates support x86_64 only.")
    base = "https://geo.mirror.pkgbuild.com/iso/latest/"
    client = SafeHttpClient(frozenset({"geo.mirror.pkgbuild.com"}))
    sums = _text(client, base + "sha256sums.txt")
    candidates = re.findall(r"\b(archlinux-(\d{4}\.\d{2}\.\d{2})-x86_64\.iso)\b", sums)
    if not candidates:
        raise ProviderError("The Arch checksum list contains no versioned x86_64 ISO.")
    filename, version = max(candidates, key=lambda item: _version_key(item[1]))
    return _artifact(
        version,
        filename,
        base + filename,
        "sha256",
        _checksum(sums, filename, "sha256"),
        {"geo.mirror.pkgbuild.com"},
    )


def _ubuntu(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.edition not in {"desktop", "live-server"} or identity.architecture not in {
        "amd64",
        "arm64",
    }:
        raise ProviderError("This Ubuntu edition or architecture has no configured official feed.")
    host = "releases.ubuntu.com"
    client = SafeHttpClient(frozenset({host}))
    index = _text(client, f"https://{host}/")
    versions = set(re.findall(r'href=["\'](\d{2}\.\d{2}(?:\.\d+)?)/', index))
    if identity.channel == "lts":
        versions = {value for value in versions if int(value[:2]) % 2 == 0 and value[3:5] == "04"}
    elif identity.channel == "interim":
        versions = {
            value for value in versions if not (int(value[:2]) % 2 == 0 and value[3:5] == "04")
        }
    else:
        raise ProviderError(f"Unsupported Ubuntu channel: {identity.channel}")
    if not versions:
        raise ProviderError("No supported Ubuntu release was found.")
    version = max(versions, key=_version_key)
    base = f"https://{host}/{version}/"
    sums = _text(client, base + "SHA256SUMS")
    filename = f"ubuntu-{version}-{identity.edition}-{identity.architecture}.iso"
    checksum = _checksum(sums, filename, "sha256")
    return _artifact(version, filename, base + filename, "sha256", checksum, {host})


def _debian(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.architecture not in {"amd64", "arm64"}:
        raise ProviderError("Debian automatic updates support amd64 and arm64 only.")
    if identity.product_id == "debian-live" or identity.edition == "live":
        if identity.architecture != "amd64" or not identity.flavor:
            raise ProviderError("Debian live updates require an amd64 desktop flavor.")
        directory = "current-live/amd64/iso-hybrid"
        pattern = rf"debian-live-(?P<version>\d+(?:\.\d+)+)-amd64-{re.escape(identity.flavor)}\.iso"
    elif identity.edition == "netinst":
        directory = f"current/{identity.architecture}/iso-cd"
        pattern = rf"debian-(?P<version>\d+(?:\.\d+)+)-{identity.architecture}-netinst\.iso"
    elif identity.edition and identity.edition.lower().startswith("dvd"):
        directory = f"current/{identity.architecture}/iso-dvd"
        number = re.search(r"\d+", identity.edition)
        disc = number.group() if number else "1"
        pattern = rf"debian-(?P<version>\d+(?:\.\d+)+)-{identity.architecture}-DVD-{disc}\.iso"
    else:
        raise ProviderError("This Debian image type has no configured official feed.")
    host = "cdimage.debian.org"
    base = f"https://{host}/debian-cd/{directory}/"
    client = SafeHttpClient(frozenset({host}))
    sums = _text(client, base + "SHA512SUMS")
    matches = list(re.finditer(pattern, sums, re.IGNORECASE))
    if not matches:
        raise ProviderError("The Debian checksum list contains no matching ISO variant.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename, version = match.group(0), match.group("version")
    return _artifact(
        version, filename, base + filename, "sha512", _checksum(sums, filename, "sha512"), {host}
    )


def _fedora(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.architecture not in {"x86_64", "aarch64"}:
        raise ProviderError("Fedora automatic updates support x86_64 and aarch64 only.")
    edition_paths = {"workstation": "Workstation", "server": "Server", "kde": "KDE"}
    try:
        edition = edition_paths[identity.edition or ""]
    except KeyError as error:
        raise ProviderError("This Fedora edition has no configured official feed yet.") from error
    host = "dl.fedoraproject.org"
    root = f"https://{host}/pub/fedora/linux/releases/"
    client = SafeHttpClient(frozenset({host}))
    versions = re.findall(r'href=["\'](\d+)/', _text(client, root))
    if not versions:
        raise ProviderError("The Fedora release directory contains no stable releases.")
    version = str(max(map(int, versions)))
    base = f"{root}{version}/{edition}/{identity.architecture}/iso/"
    listing = _text(client, base)
    iso_names = re.findall(r'href=["\']([^"\']+\.iso)["\']', listing, re.IGNORECASE)
    wanted = [name for name in iso_names if edition.lower() in name.lower()]
    if not wanted:
        raise ProviderError("The Fedora directory contains no matching ISO.")
    filename = sorted(wanted)[0]
    checksum_names = re.findall(r'href=["\']([^"\']*CHECKSUM)["\']', listing)
    if not checksum_names:
        raise ProviderError("The Fedora directory contains no CHECKSUM file.")
    sums = _text(client, base + checksum_names[0])
    build_match = re.search(rf"-{version}-(?P<build>\d+(?:\.\d+)+)", filename)
    return _artifact(
        version,
        filename,
        base + filename,
        "sha256",
        _checksum(sums, filename, "sha256"),
        {host},
        build=build_match.group("build") if build_match else None,
    )


def _linux_mint(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.edition not in {"cinnamon", "mate", "xfce"} or identity.flavor:
        raise ProviderError("The installed Linux Mint variant is not available in the stable feed.")
    hosts = {"linuxmint.com", "pub.linuxmint.io", "mirrors.kernel.org"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://linuxmint.com/download.php")
    versions = re.findall(r"\b(\d{2}(?:\.\d+){1,2})\b", page)
    if not versions:
        raise ProviderError("Could not determine the current Linux Mint version.")
    version = max(versions, key=_version_key)
    filename = f"linuxmint-{version}-{identity.edition}-64bit.iso"
    sums_url = f"https://mirrors.kernel.org/linuxmint/stable/{version}/sha256sum.txt"
    checksum = _checksum(_text(client, sums_url), filename, "sha256")
    return _artifact(
        version,
        filename,
        f"https://pub.linuxmint.io/stable/{version}/{filename}",
        "sha256",
        checksum,
        hosts,
    )


def _endeavouros(identity: IsoIdentity) -> ReleaseArtifact:
    hosts = {"endeavouros.com", "mirror.alpix.eu"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://endeavouros.com/")
    links = re.findall(r'https://mirror\.alpix\.eu/[^"\'<> ]+\.iso', page)
    if not links:
        raise ProviderError("The EndeavourOS page contains no configured official mirror link.")
    url = max(links, key=_version_key)
    filename = url.rsplit("/", 1)[-1]
    version_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", filename)
    if not version_match:
        raise ProviderError("Could not determine the EndeavourOS release date.")
    sums = _text(client, url + ".sha512sum")
    return _artifact(
        version_match.group(1), filename, url, "sha512", _checksum(sums, filename, "sha512"), hosts
    )


def _omarchy(identity: IsoIdentity) -> ReleaseArtifact:
    hosts = {"omarchy.org", "iso.omarchy.org"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://omarchy.org/")
    links = re.findall(r"https://iso\.omarchy\.org/omarchy-(\d+(?:\.\d+)+)\.iso", page)
    if not links:
        raise ProviderError("The Omarchy page contains no stable ISO link.")
    version = max(links, key=_version_key)
    filename = f"omarchy-{version}.iso"
    url = f"https://iso.omarchy.org/{filename}"
    checksum = _checksum(_text(client, url + ".sha256"), filename, "sha256")
    return _artifact(version, filename, url, "sha256", checksum, hosts)


def _manjaro(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.edition not in {"gnome", "kde", "xfce"} or identity.architecture != "x86_64":
        raise ProviderError("This Manjaro edition or architecture has no configured official feed.")
    if identity.channel != "stable":
        raise ProviderError("Manjaro review/preview updates require an explicit channel mapping.")
    host = "download.manjaro.org"
    client = SafeHttpClient(frozenset({host}))
    root = f"https://{host}/{identity.edition}/"
    versions = re.findall(r'href=["\']([^/"\']+)/', _text(client, root))
    versions = [value for value in versions if re.fullmatch(r"\d+(?:\.\d+)+", value)]
    if not versions:
        raise ProviderError("The Manjaro directory contains no stable release.")
    version = max(versions, key=_version_key)
    base = urljoin(root, version + "/")
    listing = _text(client, base)
    filenames = re.findall(r'href=["\'](manjaro-[^"\']+\.iso)["\']', listing)
    minimal = identity.flavor == "minimal"
    candidates = [name for name in filenames if ("-minimal-" in name) == minimal]
    if not candidates:
        raise ProviderError("The Manjaro directory contains no matching full/minimal ISO.")
    filename = sorted(candidates, key=_version_key)[-1]
    build = (re.search(r"-(\d{6})-linux", filename) or [None, None])[1]
    sums = _text(client, base + filename + ".sha256")
    return _artifact(
        version,
        filename,
        base + filename,
        "sha256",
        _checksum(sums, filename, "sha256"),
        {host},
        build=build,
    )


def _pop_os(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.edition not in {"generic", "nvidia"} or identity.architecture not in {
        "amd64",
        "arm64",
    }:
        raise ProviderError("This Pop!_OS variant has no configured official feed.")
    hosts = {"api.pop-os.org", "iso.pop-os.org"}
    client = SafeHttpClient(frozenset(hosts))
    version = "24.04"
    payload = json.loads(
        _text(
            client,
            f"https://api.pop-os.org/builds/{version}/{identity.edition}"
            f"?arch={identity.architecture}",
        )
    )
    url = str(payload.get("url", ""))
    filename = url.rsplit("/", 1)[-1]
    checksum = str(payload.get("sha_sum", ""))
    if not re.fullmatch(r"[A-Fa-f0-9]{64}", checksum) or not re.fullmatch(
        rf"pop-os_{re.escape(version)}_{identity.architecture}_{identity.edition}_\d+\.iso",
        filename,
    ):
        raise ProviderError("The Pop!_OS API returned invalid artifact metadata.")
    return _artifact(
        str(payload.get("version", version)),
        filename,
        url,
        "sha256",
        checksum.lower(),
        hosts,
        build=str(payload.get("build")),
        size_bytes=int(payload["size"]),
    )


def _vanilla_os(identity: IsoIdentity) -> ReleaseArtifact:
    architecture = "arm64" if identity.architecture in {"arm64", "aarch64"} else "amd64"
    hosts = {
        "api.github.com",
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    }
    client = SafeHttpClient(frozenset(hosts))
    payload = json.loads(
        _text(client, "https://api.github.com/repos/Vanilla-OS/live-iso/releases/latest")
    )
    assets = {asset["name"]: asset["browser_download_url"] for asset in payload.get("assets", [])}
    pattern = re.compile(
        rf"Vanilla-OS-(?P<version>\d+(?:\.\d+)*)-stable-{architecture}\.(?P<build>\d{{8}})\.iso$"
    )
    matches: list[tuple[str, re.Match[str]]] = []
    for name in assets:
        if match := pattern.fullmatch(name):
            matches.append((name, match))
    if not matches:
        raise ProviderError("The Vanilla OS release contains no matching stable ISO.")
    filename, match = max(
        matches, key=lambda item: (_version_key(item[1].group("version")), item[1].group("build"))
    )
    checksum_name = filename.removesuffix(".iso") + ".sha256.txt"
    if checksum_name not in assets:
        raise ProviderError("The Vanilla OS release lacks its SHA-256 asset.")
    checksum = _checksum(_text(client, assets[checksum_name]), filename, "sha256")
    return _artifact(
        match.group("version"),
        filename,
        assets[filename],
        "sha256",
        checksum,
        hosts,
        build=match.group("build"),
    )


def _zorin_os(identity: IsoIdentity) -> ReleaseArtifact:
    edition = (identity.edition or "").title()
    if edition not in {"Core", "Education", "Lite"}:
        raise ProviderError("Paid or unknown Zorin OS editions cannot be downloaded automatically.")
    hosts = {"zorin.com", "help.zorin.com", "zrn.co", "mirror.dogado.de"}
    client = SafeHttpClient(frozenset(hosts))
    integrity_url = (
        "https://help.zorin.com/docs/getting-started/check-the-integrity-of-your-copy-of-zorin-os/"
    )
    page = _text(client, integrity_url)
    pattern = (
        rf"Zorin OS (?P<version>\d+(?:\.\d+)+) {edition} 64-bit"
        r"(?: \(r(?P<build>\d+)\))?.{0,500}?"
        r"(?P<hash>[A-Fa-f0-9]{64})"
    )
    matches = list(re.finditer(pattern, page, re.IGNORECASE | re.DOTALL))
    if not matches:
        raise ProviderError("The Zorin integrity page contains no checksum for this free edition.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    version, build = match.group("version"), match.group("build")
    suffix = f"-r{build}" if build else ""
    filename = f"Zorin-OS-{version}-{edition}-64-bit{suffix}.iso"
    if edition == "Lite":
        url = f"https://zrn.co/{version.split('.', 1)[0]}lite64"
    else:
        url = f"https://zorin.com/os/download/{version.split('.', 1)[0]}/{edition.lower()}/"
    return _artifact(
        version, filename, url, "sha256", match.group("hash").lower(), hosts, build=build
    )
