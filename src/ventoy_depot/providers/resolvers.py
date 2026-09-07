from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import replace

from ..models import IsoIdentity, ReleaseArtifact
from ..network import SafeHttpClient
from .base import ProviderError

BUILTIN_RESOLVER_IDS = frozenset(
    {
        "arch",
        "adelie-linux",
        "artix-linux",
        "backbox",
        "alpine",
        "chimera-linux",
        "rocky-linux",
        "almalinux",
        "oracle-linux",
        "ubuntu",
        "ubuntu-flavors",
        "debian",
        "devuan",
        "fedora",
        "fedora-coreos",
        "flatcar",
        "linux-mint",
        "endeavouros",
        "cachyos",
        "clonezilla",
        "gparted-live",
        "finnix",
        "alt-rescue",
        "urbackup-restore",
        "kali-linux",
        "kaos",
        "nixos",
        "nobara",
        "systemrescue",
        "super-grub2-disk",
        "opensuse-tumbleweed",
        "opensuse-leap",
        "freebsd",
        "openbsd",
        "omnios",
        "omarchy",
        "manjaro",
        "pop-os",
        "proxmox",
        "rescuezilla",
        "vanilla-os",
        "zorin-os",
        "netboot-xyz",
        "gentoo",
        "hirens-bootcd-pe",
        "shredos",
        "netbsd",
        "openindiana",
        "xcp-ng",
        "porteux",
        "ghostbsd",
        "haiku",
        "harvester",
        "solus",
        "truenas",
        "tuxedo-os",
        "tails",
        "grml",
        "kde-neon",
        "parrot-os",
        "void-linux",
        "mageia",
        "centos-stream",
        "bunsenlabs",
        "security-onion",
        "talos-linux",
        "antix",
        "mx-linux",
        "caine",
        "kaisen-linux",
        "casuarina-linux",
    }
)


def resolve_release(provider_id: str, identity: IsoIdentity) -> ReleaseArtifact:
    resolvers = {
        "arch": _arch,
        "adelie-linux": _adelie_linux,
        "artix-linux": _artix_linux,
        "backbox": _backbox,
        "alpine": _alpine,
        "chimera-linux": _chimera_linux,
        "rocky-linux": _rocky_linux,
        "almalinux": _almalinux,
        "oracle-linux": _oracle_linux,
        "ubuntu": _ubuntu,
        "ubuntu-flavors": _ubuntu_flavors,
        "debian": _debian,
        "devuan": _devuan,
        "fedora": _fedora,
        "fedora-coreos": _fedora_coreos,
        "flatcar": _flatcar,
        "linux-mint": _linux_mint,
        "endeavouros": _endeavouros,
        "cachyos": _cachyos,
        "clonezilla": _clonezilla,
        "gparted-live": _gparted_live,
        "finnix": _finnix,
        "alt-rescue": _alt_rescue,
        "urbackup-restore": _urbackup_restore,
        "kali-linux": _kali_linux,
        "kaos": _kaos,
        "nixos": _nixos,
        "nobara": _nobara,
        "systemrescue": _systemrescue,
        "super-grub2-disk": _super_grub2_disk,
        "opensuse-tumbleweed": _opensuse_tumbleweed,
        "opensuse-leap": _opensuse_leap,
        "freebsd": _freebsd,
        "openbsd": _openbsd,
        "omnios": _omnios,
        "omarchy": _omarchy,
        "manjaro": _manjaro,
        "pop-os": _pop_os,
        "proxmox": _proxmox,
        "rescuezilla": _rescuezilla,
        "vanilla-os": _vanilla_os,
        "zorin-os": _zorin_os,
        "netboot-xyz": _netboot_xyz,
        "gentoo": _gentoo,
        "hirens-bootcd-pe": _hirens_bootcd_pe,
        "shredos": _shredos,
        "netbsd": _netbsd,
        "openindiana": _openindiana,
        "xcp-ng": _xcp_ng,
        "porteux": _porteux,
        "ghostbsd": _ghostbsd,
        "haiku": _haiku,
        "harvester": _harvester,
        "solus": _solus,
        "truenas": _truenas,
        "tuxedo-os": _tuxedo_os,
        "tails": _tails,
        "grml": _grml,
        "kde-neon": _kde_neon,
        "parrot-os": _parrot_os,
        "void-linux": _void_linux,
        "mageia": _mageia,
        "centos-stream": _centos_stream,
        "bunsenlabs": _bunsenlabs,
        "security-onion": _security_onion,
        "talos-linux": _talos_linux,
        "antix": _antix,
        "mx-linux": _mx_linux,
        "caine": _caine,
        "kaisen-linux": _kaisen_linux,
        "casuarina-linux": _casuarina_linux,
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
    identity: IsoIdentity,
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
        identity=replace(identity, version=version, build=build),
    )


def _text(client: SafeHttpClient, url: str) -> str:
    return client.metadata(url).decode("utf-8", errors="replace")


def _checksum(text: str, filename: str, algorithm: str) -> str:
    length = 64 if algorithm == "sha256" else 128
    escaped = re.escape(filename)
    patterns = (
        rf"^(?P<hash>[A-Fa-f0-9]{{{length}}})\s+[* ]?{escaped}\s*$",
        rf"^{algorithm.upper()}\s*\({escaped}\)\s*=\s*(?P<hash>[A-Fa-f0-9]{{{length}}})\s*$",
        rf"{escaped}.{{0,500}}?(?P<hash>[A-Fa-f0-9]{{{length}}})",
    )
    for pattern in patterns:
        if match := re.search(pattern, text, re.MULTILINE | re.DOTALL):
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
        identity,
        version,
        filename,
        base + filename,
        "sha256",
        _checksum(sums, filename, "sha256"),
        {"geo.mirror.pkgbuild.com"},
    )


def _adelie_linux(identity: IsoIdentity) -> ReleaseArtifact:
    architectures = {"aarch64", "armv7", "pmmx", "ppc", "ppc64", "x86_64"}
    if identity.architecture not in architectures or identity.channel != "beta":
        raise ProviderError("This Adélie Linux architecture or release channel is unsupported.")
    if identity.edition == "inst":
        prefix = f"adelie-inst-{identity.architecture}"
        if identity.flavor is not None:
            raise ProviderError("Adélie installer ISOs do not have a desktop flavor.")
    elif identity.edition == "live" and identity.flavor in {"kde", "lxqt", "mate", "xfce"}:
        prefix = f"adelie-live-{identity.flavor}-{identity.architecture}"
    else:
        raise ProviderError("This Adélie Linux ISO edition or desktop is unsupported.")
    host = "distfiles.adelielinux.org"
    client = SafeHttpClient(frozenset({host}))
    base = f"https://{host}/adelie/current/iso/"
    expression = re.compile(
        rf"\b(?P<filename>{re.escape(prefix)}-(?P<version>\d+\.\d+-beta\d+)-"
        rf"(?P<build>\d{{8}})\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(_text(client, base)))
    if not matches:
        raise ProviderError("The Adélie current directory lacks this ISO variant.")
    match = max(matches, key=lambda item: _version_key(item.group("build")))
    filename, version, build = (
        match.group("filename"),
        match.group("version"),
        match.group("build"),
    )
    sums = _text(client, base + "SHA512SUMS")
    return _artifact(
        identity,
        version,
        filename,
        base + filename,
        "sha512",
        _checksum(sums, filename, "sha512"),
        {host},
        build=build,
    )


def _artix_linux(identity: IsoIdentity) -> ReleaseArtifact:
    editions = {
        "base",
        "cinnamon",
        "community-gtk",
        "community-qt",
        "lxqt",
        "mate",
        "plasma",
        "xfce",
    }
    flavors = {"dinit", "openrc", "runit", "s6"}
    if (
        identity.channel != "stable"
        or identity.architecture != "x86_64"
        or identity.edition not in editions
        or identity.flavor not in flavors
    ):
        raise ProviderError("This Artix edition, init system or channel is not supported.")
    hosts = {
        "artixlinux.org",
        "iso.artixlinux.org",
        "download.artixlinux.org",
        "mirror3.artixlinux.org",
    }
    client = SafeHttpClient(frozenset(hosts))
    page_url = "https://iso.artixlinux.org/iso/"
    page = _text(client, page_url)
    expression = re.compile(
        rf"(?P<url>https://(?:download|mirror3)\.artixlinux\.org/iso/"
        rf"(?P<filename>artix-{re.escape(identity.edition)}-"
        rf"{re.escape(identity.flavor)}-(?P<version>\d{{8}})-x86_64\.iso))\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(page))
    if not matches:
        raise ProviderError("The Artix stable page lacks this edition and init-system pair.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    upstream_name, version = match.group("filename"), match.group("version")
    checksum = _checksum(page, upstream_name, "sha256")
    filename = f"artix-stable-{identity.edition}-{identity.flavor}-{version}-x86_64.iso"
    return _artifact(
        identity,
        version,
        filename,
        match.group("url"),
        "sha256",
        checksum,
        hosts,
    )


def _backbox(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.edition != "desktop" or identity.architecture != "amd64":
        raise ProviderError("BackBox automatic updates support the amd64 desktop ISO only.")
    hosts = {"www.backbox.org", "linux.backbox.org", "backbox.mirror.garr.it"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://www.backbox.org/download/")
    names = re.findall(r"\b(backbox-(?P<version>\d+(?:\.\d+)*)-desktop-amd64\.iso)\b", page)
    if not names:
        raise ProviderError("The official BackBox page contains no desktop ISO metadata.")
    filename, version = max(names, key=lambda item: _version_key(item[1]))
    checksum = _checksum(page, filename, "sha256")
    url = f"https://backbox.mirror.garr.it/{filename}"
    return _artifact(identity, version, filename, url, "sha256", checksum, hosts)


def _alpine(identity: IsoIdentity) -> ReleaseArtifact:
    editions = {"standard", "extended", "virtual", "xen"}
    architectures = {
        "x86",
        "x86_64",
        "aarch64",
        "armv7",
        "loongarch64",
        "ppc64le",
        "riscv64",
        "s390x",
    }
    if identity.edition not in editions or identity.architecture not in architectures:
        raise ProviderError("This Alpine image type or architecture is not supported.")
    if identity.edition == "extended" and identity.architecture not in {"x86", "x86_64"}:
        raise ProviderError("Alpine Extended is published for x86 and x86_64 only.")
    if identity.edition == "xen" and identity.architecture != "x86_64":
        raise ProviderError("Alpine Xen is published for x86_64 only.")
    hosts = {"www.alpinelinux.org", "dl-cdn.alpinelinux.org"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://www.alpinelinux.org/downloads/")
    pattern = re.compile(
        rf'https://dl-cdn\.alpinelinux\.org/alpine/[^"\'<> ]+/releases/'
        rf"{re.escape(identity.architecture)}/"
        rf"(alpine-{re.escape(identity.edition)}-(?P<version>\d+(?:\.\d+)+)-"
        rf"{re.escape(identity.architecture)}\.iso)"
    )
    matches = list(pattern.finditer(page))
    if not matches:
        raise ProviderError("The Alpine downloads page contains no matching stable ISO.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename, version = match.group(1), match.group("version")
    url = match.group(0)
    checksum = _checksum(_text(client, url + ".sha256"), filename, "sha256")
    return _artifact(identity, version, filename, url, "sha256", checksum, hosts)


def _enterprise_linux(
    identity: IsoIdentity,
    *,
    provider_id: str,
    product_name: str,
    host: str,
    root: str,
) -> ReleaseArtifact:
    if identity.channel not in {"8", "9", "10"}:
        raise ProviderError(f"Unsupported {product_name} major-release channel.")
    if identity.edition not in {"boot", "dvd", "dvd1", "minimal"}:
        raise ProviderError(f"Unsupported {product_name} ISO edition.")
    if identity.flavor not in {None, "latest-alias"}:
        raise ProviderError(f"Unsupported {product_name} ISO flavor.")
    client = SafeHttpClient(frozenset({host}))
    base = root.format(channel=identity.channel, architecture=identity.architecture)
    sums = _text(client, base + "CHECKSUM")
    if provider_id == "rocky-linux":
        prefix = "Rocky"
        edition = identity.edition
    else:
        prefix = "AlmaLinux"
        edition = identity.edition
    pattern = re.compile(
        rf"\b({prefix}-(?P<version>{re.escape(identity.channel)}\.\d+)-"
        rf"{re.escape(identity.architecture)}-{re.escape(edition)}\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(sums))
    if not matches:
        raise ProviderError(f"The official {product_name} checksum list has no matching ISO.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename, version = match.group(1), match.group("version")
    return _artifact(
        identity,
        version,
        filename,
        base + filename,
        "sha256",
        _checksum(sums, filename, "sha256"),
        {host},
    )


def _chimera_linux(identity: IsoIdentity) -> ReleaseArtifact:
    architectures = {
        "aarch64",
        "loongarch64",
        "ppc",
        "ppc64",
        "ppc64le",
        "riscv64",
        "x86_64",
    }
    if (
        identity.edition not in {"base", "gnome", "plasma"}
        or identity.architecture not in architectures
    ):
        raise ProviderError("This Chimera Linux desktop or architecture is not supported.")
    host = "repo.chimera-linux.org"
    client = SafeHttpClient(frozenset({host}))
    base = f"https://{host}/live/latest/"
    expression = re.compile(
        rf"(?P<filename>chimera-linux-{re.escape(identity.architecture)}-LIVE-"
        rf"(?P<version>\d{{8}})-{re.escape(identity.edition)}\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(_text(client, base)))
    if not matches:
        raise ProviderError("The Chimera Linux release index lacks this ISO variant.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename, version = match.group("filename"), match.group("version")
    checksum = _checksum(_text(client, base + "sha256sums.txt"), filename, "sha256")
    return _artifact(identity, version, filename, base + filename, "sha256", checksum, {host})


def _rocky_linux(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.architecture not in {"x86_64", "aarch64"}:
        raise ProviderError("Rocky Linux automatic updates support x86_64 and aarch64 only.")
    return _enterprise_linux(
        identity,
        provider_id="rocky-linux",
        product_name="Rocky Linux",
        host="download.rockylinux.org",
        root=("https://download.rockylinux.org/pub/rocky/{channel}/isos/{architecture}/"),
    )


def _almalinux(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.architecture not in {"x86_64", "x86_64_v2", "aarch64", "ppc64le", "s390x"}:
        raise ProviderError("This AlmaLinux architecture is not supported.")
    return _enterprise_linux(
        identity,
        provider_id="almalinux",
        product_name="AlmaLinux",
        host="repo.almalinux.org",
        root="https://repo.almalinux.org/almalinux/{channel}/isos/{architecture}/",
    )


def _oracle_linux(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "oracle-linux" or identity.edition not in {
        "dvd",
        "boot",
        "boot-uek",
    }:
        raise ProviderError("This Oracle Linux installation medium is not supported.")
    if identity.channel not in {"8", "9", "10"} or identity.architecture not in {
        "x86_64",
        "aarch64",
    }:
        raise ProviderError("This Oracle Linux release channel or architecture is unsupported.")
    hosts = {"yum.oracle.com", "linux.oracle.com"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://yum.oracle.com/oracle-linux-isos.html")
    expression = re.compile(
        rf"https://yum\.oracle\.com/ISOS/OracleLinux/OL{re.escape(identity.channel)}/"
        rf"u(?P<update>\d+)/{re.escape(identity.architecture)}/"
        rf"(?P<filename>OracleLinux-R(?P<version>{re.escape(identity.channel)}-U(?P=update))-"
        rf"(?:Server-)?{re.escape(identity.architecture)}-{re.escape(identity.edition)}\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(page))
    if not matches:
        raise ProviderError("The official Oracle Linux page lacks the selected ISO variant.")
    match = max(matches, key=lambda item: int(item.group("update")))
    filename, url = match.group("filename"), match.group(0)
    checksum_url = (
        "https://linux.oracle.com/security/gpg/checksum/"
        f"OracleLinux-R{identity.channel}-U{match.group('update')}-Server-"
        f"{identity.architecture}.checksum"
    )
    checksum = _checksum(_text(client, checksum_url), filename, "sha256")
    return _artifact(
        identity,
        match.group("version"),
        filename,
        url,
        "sha256",
        checksum,
        hosts,
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
    return _artifact(identity, version, filename, base + filename, "sha256", checksum, {host})


def _ubuntu_flavors(identity: IsoIdentity) -> ReleaseArtifact:
    products = {
        "kubuntu",
        "lubuntu",
        "xubuntu",
        "ubuntu-budgie",
        "ubuntu-unity",
        "ubuntu-mate",
        "ubuntucinnamon",
        "edubuntu",
        "ubuntustudio",
        "ubuntukylin",
    }
    if (
        identity.product_id not in products
        or identity.edition != "desktop"
        or identity.architecture != "amd64"
    ):
        raise ProviderError("This Ubuntu flavor variant has no configured official feed.")
    host = "cdimage.ubuntu.com"
    client = SafeHttpClient(frozenset({host}))
    root = f"https://{host}/{identity.product_id}/releases/"
    index = _text(client, root)
    versions = set(re.findall(r'href=["\'](\d{2}\.\d{2}(?:\.\d+)?)/', index))
    if identity.channel == "lts":
        versions = {value for value in versions if int(value[:2]) % 2 == 0 and value[3:5] == "04"}
    elif identity.channel == "interim":
        versions = {
            value for value in versions if not (int(value[:2]) % 2 == 0 and value[3:5] == "04")
        }
    else:
        raise ProviderError(f"Unsupported Ubuntu flavor channel: {identity.channel}")
    if not versions:
        raise ProviderError("No supported Ubuntu flavor release was found.")
    version = max(versions, key=_version_key)
    base = f"{root}{version}/release/"
    sums = _text(client, base + "SHA256SUMS")
    filename = f"{identity.product_id}-{version}-desktop-amd64.iso"
    checksum = _checksum(sums, filename, "sha256")
    return _artifact(identity, version, filename, base + filename, "sha256", checksum, {host})


def _debian(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.architecture not in {"amd64", "arm64"}:
        raise ProviderError("Debian automatic updates support amd64 and arm64 only.")
    if identity.product_id == "debian-live" or identity.edition == "live":
        if identity.architecture != "amd64" or not identity.flavor:
            raise ProviderError("Debian live updates require an amd64 desktop flavor.")
        directory = "current-live/amd64/iso-hybrid"
        pattern = rf"debian-live-(?P<version>\d+(?:\.\d+)+)-amd64-{re.escape(identity.flavor)}\.iso"
    elif identity.flavor is not None:
        raise ProviderError("Non-live Debian images cannot carry a desktop flavor.")
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
        identity,
        version,
        filename,
        base + filename,
        "sha512",
        _checksum(sums, filename, "sha512"),
        {host},
    )


def _fedora(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.architecture not in {"x86_64", "aarch64"}:
        raise ProviderError("Fedora automatic updates support x86_64 and aarch64 only.")
    edition_paths = {
        "workstation": ("Workstation", "Workstation", "live"),
        "server": ("Server", "Server", "dvd"),
        "kde": ("KDE", "KDE", "live"),
        "kde-desktop": ("KDE", "KDE", "live"),
        "silverblue": ("Silverblue", "Silverblue", "ostree"),
        "budgie": ("Spins", "Budgie", "live"),
        "cosmic": ("Spins", "COSMIC", "live"),
        "cinnamon": ("Spins", "Cinnamon", "live"),
        "kde-mobile": ("Spins", "KDE-Mobile", "live"),
        "lxde": ("Spins", "LXDE", "live"),
        "lxqt": ("Spins", "LXQt", "live"),
        "mate_compiz": ("Spins", "MATE_Compiz", "live"),
        "miraclewm": ("Spins", "MiracleWM", "live"),
        "soas": ("Spins", "SoaS", "live"),
        "sway": ("Spins", "Sway", "live"),
        "xfce": ("Spins", "Xfce", "live"),
        "i3": ("Spins", "i3", "live"),
    }
    try:
        directory, image_name, expected_flavor = edition_paths[identity.edition or ""]
    except KeyError as error:
        raise ProviderError("This Fedora edition has no configured official feed yet.") from error
    if identity.flavor != expected_flavor:
        raise ProviderError("The Fedora edition and image flavor do not form a supported variant.")
    if directory == "Spins" and identity.architecture != "x86_64":
        raise ProviderError("The selected Fedora Spin is currently published for x86_64 only.")
    host = "dl.fedoraproject.org"
    root = f"https://{host}/pub/fedora/linux/releases/"
    client = SafeHttpClient(frozenset({host}))
    versions = re.findall(r'href=["\'](\d+)/', _text(client, root))
    if not versions:
        raise ProviderError("The Fedora release directory contains no stable releases.")
    version = str(max(map(int, versions)))
    base = f"{root}{version}/{directory}/{identity.architecture}/iso/"
    listing = _text(client, base)
    iso_names = re.findall(r'href=["\']([^"\']+\.iso)["\']', listing, re.IGNORECASE)
    wanted = [
        name
        for name in iso_names
        if re.search(rf"^Fedora-{re.escape(image_name)}(?:-|_)", name, re.IGNORECASE)
    ]
    if not wanted:
        raise ProviderError("The Fedora directory contains no matching ISO.")
    filename = sorted(wanted)[0]
    checksum_names = re.findall(r'href=["\']([^"\']*CHECKSUM)["\']', listing)
    if not checksum_names:
        raise ProviderError("The Fedora directory contains no CHECKSUM file.")
    sums = _text(client, base + checksum_names[0])
    build_match = re.search(rf"-{version}-(?P<build>\d+(?:\.\d+)+)", filename)
    return _artifact(
        identity,
        version,
        filename,
        base + filename,
        "sha256",
        _checksum(sums, filename, "sha256"),
        {host},
        build=build_match.group("build") if build_match else None,
    )


def _fedora_coreos(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "fedora-coreos" or identity.edition != "live-iso":
        raise ProviderError("Only Fedora CoreOS live ISOs are supported.")
    if identity.architecture not in {"x86_64", "aarch64"}:
        raise ProviderError("This Fedora CoreOS architecture is not supported.")
    if identity.channel not in {"stable", "testing", "next"}:
        raise ProviderError("This Fedora CoreOS release stream is not supported.")
    host = "builds.coreos.fedoraproject.org"
    client = SafeHttpClient(frozenset({host}))
    metadata_url = f"https://{host}/streams/{identity.channel}.json"
    payload = json.loads(_text(client, metadata_url))
    try:
        metal = payload["architectures"][identity.architecture]["artifacts"]["metal"]
        version = str(metal["release"])
        disk = metal["formats"]["iso"]["disk"]
        url = str(disk["location"])
        checksum = str(disk["sha256"]).lower()
    except (KeyError, TypeError) as error:
        raise ProviderError("The Fedora CoreOS stream lacks the selected live ISO.") from error
    upstream_name = url.rsplit("/", 1)[-1]
    expected_name = f"fedora-coreos-{version}-live-iso.{identity.architecture}.iso"
    if upstream_name != expected_name or not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ProviderError("The Fedora CoreOS stream returned invalid ISO metadata.")
    target_name = f"fedora-coreos-{identity.channel}-{version}-live-iso.{identity.architecture}.iso"
    return _artifact(
        identity,
        version,
        target_name,
        url,
        "sha256",
        checksum,
        {host},
    )


def _flatcar(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "flatcar" or identity.edition != "live-iso":
        raise ProviderError("Only Flatcar Container Linux live ISOs are supported.")
    if identity.architecture != "amd64" or identity.channel not in {
        "stable",
        "beta",
        "alpha",
        "lts",
    }:
        raise ProviderError("This Flatcar architecture or release channel is unsupported.")
    host = f"{identity.channel}.release.flatcar-linux.net"
    hosts = {host, "flatcar.cdn.cncf.io"}
    client = SafeHttpClient(frozenset(hosts))
    root = f"https://{host}/amd64-usr/"
    version_text = _text(client, root + "current/version.txt")
    version_match = re.search(
        r"^FLATCAR_VERSION_ID=(?P<version>\d+(?:\.\d+)+)$", version_text, re.M
    )
    if version_match is None:
        raise ProviderError("The official Flatcar metadata lacks a release version.")
    version = version_match.group("version")
    upstream_name = "flatcar_production_iso_image.iso"
    base = f"{root}{version}/"
    sums = _text(client, base + upstream_name + ".DIGESTS")
    target_name = f"flatcar-{identity.channel}-{version}-amd64.iso"
    return _artifact(
        identity,
        version,
        target_name,
        base + upstream_name,
        "sha512",
        _checksum(sums, upstream_name, "sha512"),
        hosts,
    )


def _linux_mint(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.flavor == "edge":
        raise ProviderError(
            "The historical Linux Mint Edge image was discontinued. Assign it to the standard "
            "edition explicitly before updating."
        )
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
        identity,
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
    page = _text(client, "https://endeavouros.com/download/")
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
        identity,
        version_match.group(1),
        filename,
        url,
        "sha512",
        _checksum(sums, filename, "sha512"),
        hosts,
    )


def _cachyos(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.edition == "kde":
        raise ProviderError(
            "The historical CachyOS KDE image was discontinued. Assign it to the current "
            "desktop edition explicitly before updating."
        )
    if identity.edition not in {"desktop", "handheld"} or identity.architecture != "x86_64":
        raise ProviderError("This CachyOS edition or architecture is not supported.")
    if identity.flavor or identity.channel != "stable":
        raise ProviderError("CachyOS automatic updates support stable unmodified images only.")
    host = "mirror.cachyos.org"
    client = SafeHttpClient(frozenset({host}))
    root = f"https://{host}/ISO/{identity.edition}/"
    releases = re.findall(r'href=["\'](?P<version>\d{6})/["\']', _text(client, root))
    if not releases:
        raise ProviderError("The official CachyOS directory contains no releases.")
    version = max(releases, key=_version_key)
    base = f"{root}{version}/"
    filename = f"cachyos-{identity.edition}-linux-{version}.iso"
    checksum = _checksum(_text(client, base + filename + ".sha256"), filename, "sha256")
    return _artifact(identity, version, filename, base + filename, "sha256", checksum, {host})


def _clonezilla(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.edition not in {"debian", "ubuntu"} or identity.architecture != "amd64":
        raise ProviderError("This Clonezilla edition or architecture is not supported.")
    branch = "stable" if identity.edition == "debian" else "alternative"
    hosts = {"clonezilla.org", "downloads.sourceforge.net", "sourceforge.net"}
    client = SafeHttpClient(frozenset(hosts))
    sums = _text(client, f"https://clonezilla.org/downloads/{branch}/checksums.php")
    pattern = re.compile(r"\b(clonezilla-live-(?P<version>[\w.-]+)-amd64\.iso)\b")
    matches = list(pattern.finditer(sums))
    if not matches:
        raise ProviderError("The official Clonezilla checksum page contains no amd64 ISO.")
    match = matches[0]
    filename, version = match.group(1), match.group("version")
    project = "clonezilla_live_stable" if branch == "stable" else "clonezilla_live_alternative"
    url = f"https://downloads.sourceforge.net/clonezilla/{project}/{version}/{filename}"
    return _artifact(
        identity,
        version,
        filename,
        url,
        "sha256",
        _checksum(sums, filename, "sha256"),
        hosts,
    )


def _gparted_live(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.edition != "live" or identity.architecture != "amd64" or identity.flavor:
        raise ProviderError("GParted Live automatic updates support the stable amd64 ISO only.")
    hosts = {
        "gparted.org",
        "downloads.sourceforge.net",
        "sourceforge.net",
        "netcologne.dl.sourceforge.net",
    }
    client = SafeHttpClient(frozenset(hosts))
    sums = _text(client, "https://gparted.org/gparted-live/stable/CHECKSUMS.TXT")
    candidates = re.findall(r"\b(gparted-live-(\d+(?:\.\d+)+-\d+)-amd64\.iso)\b", sums)
    if not candidates:
        raise ProviderError("The official GParted checksum list contains no amd64 ISO.")
    filename, version = max(candidates, key=lambda item: _version_key(item[1]))
    url = (
        "https://downloads.sourceforge.net/project/gparted/gparted-live-stable/"
        f"{version}/{filename}?use_mirror=netcologne"
    )
    return _artifact(
        identity,
        version,
        filename,
        url,
        "sha256",
        _checksum(sums, filename, "sha256"),
        hosts,
    )


def _finnix(identity: IsoIdentity) -> ReleaseArtifact:
    if (
        identity.product_id != "finnix"
        or identity.edition != "live"
        or identity.architecture != "amd64"
        or identity.channel != "stable"
        or identity.flavor
        or identity.language
    ):
        raise ProviderError("Finnix automatic updates support the stable amd64 ISO only.")
    hosts = {"www.finnix.org", "forge.colobox.com"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://www.finnix.org/")
    matches = list(
        re.finditer(
            r"https://www\.finnix\.org/releases/(?P<version>\d+(?:\.\d+)?)/"
            r"(?P<filename>finnix-(?P=version)\.iso)",
            page,
            re.IGNORECASE,
        )
    )
    if not matches:
        raise ProviderError("The official Finnix page contains no stable ISO.")
    selected = max(matches, key=lambda item: _version_key(item.group("version")))
    version = selected.group("version")
    filename = selected.group("filename")
    release_url = (
        f"https://forge.colobox.com/finnix/finnix-docs/raw/branch/main/releases/{version}.json"
    )
    payload = json.loads(_text(client, release_url))
    try:
        file_data = payload["finnix"]["releases"][version]["architectures"]["amd64"]["files"][
            filename
        ]
        checksums = file_data["checksums"]
        checksum = checksums["sha512"]
        size = file_data["size"]
    except (KeyError, TypeError) as error:
        raise ProviderError("The official Finnix release data lacks the selected ISO.") from error
    if not isinstance(checksum, str) or not re.fullmatch(r"[A-Fa-f0-9]{128}", checksum):
        raise ProviderError("The official Finnix release data lacks a valid SHA-512 digest.")
    if not isinstance(size, int) or size <= 0:
        raise ProviderError("The official Finnix release data lacks a valid ISO size.")
    url = f"https://www.finnix.org/releases/{version}/{filename}"
    return _artifact(
        identity,
        version,
        filename,
        url,
        "sha512",
        checksum.lower(),
        hosts,
        size_bytes=size,
    )


def _alt_rescue(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "alt-rescue" or identity.channel not in {"p10", "p11"}:
        raise ProviderError("This ALT Rescue product or platform channel is unsupported.")
    valid_variants = {
        ("p10", "rescue", "i586"),
        ("p10", "rescue", "x86_64"),
        ("p11", "rescue", "x86_64"),
        ("p11", "rescue-live", "x86_64"),
    }
    if (identity.channel, identity.edition, identity.architecture) not in valid_variants:
        raise ProviderError("This ALT Rescue edition and architecture combination is unavailable.")
    if identity.flavor or identity.language:
        raise ProviderError("ALT Rescue does not publish flavor or language-specific ISOs.")
    host = "nightly.altlinux.org"
    base = f"https://{host}/{identity.channel}/release/"
    client = SafeHttpClient(frozenset({host}))
    sums = _text(client, base + "SHA512SUM")
    expression = re.compile(
        rf"\b(alt-{re.escape(identity.channel)}-{re.escape(identity.edition or '')}-"
        rf"(?P<version>\d{{8}})-{re.escape(identity.architecture)}\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(sums))
    if not matches:
        raise ProviderError("The official ALT checksum list lacks this Rescue ISO variant.")
    match = max(matches, key=lambda item: item.group("version"))
    filename, version = match.group(1), match.group("version")
    checksum = _checksum(sums, filename, "sha512")
    return _artifact(identity, version, filename, base + filename, "sha512", checksum, {host})


def _devuan(identity: IsoIdentity) -> ReleaseArtifact:
    installer_editions = {"netinstall", "server", "desktop", "cd2", "cd3", "cd4", "cd5", "pool1"}
    if identity.edition not in installer_editions | {"desktop-live"}:
        raise ProviderError("This Devuan installer or live variant is not supported.")
    if identity.architecture != "amd64" or identity.channel != "stable" or identity.flavor:
        raise ProviderError("Devuan automatic updates support stable amd64 images only.")
    hosts = {"files.devuan.org", "www.devuan.org"}
    client = SafeHttpClient(frozenset(hosts))
    root = "https://files.devuan.org/"
    root_page = _text(client, root)
    release = re.search(
        r'href="https://www\.devuan\.org/os/announce/(?P<codename>[a-z]+)-release-announce-'
        r'[^"/]+">Current Release Announcement</a>',
        root_page,
        re.IGNORECASE,
    )
    if release is None:
        raise ProviderError("Could not identify Devuan's current stable release directory.")
    codename = release.group("codename").lower()
    directory = "desktop-live" if identity.edition == "desktop-live" else "installer-iso"
    base = f"{root}devuan_{codename}/{directory}/"
    listing = _text(client, base)
    pattern = re.compile(
        rf"devuan_{re.escape(codename)}_(?P<version>\d+(?:\.\d+)+)_amd64_"
        rf"{re.escape(identity.edition)}\.iso",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(listing))
    if not matches:
        raise ProviderError("The Devuan release contains no matching ISO variant.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename = match.group(0)
    sums_url = base + (filename + ".sha256" if directory == "desktop-live" else "SHA256SUMS.txt")
    checksum = _checksum(_text(client, sums_url), filename, "sha256")
    return _artifact(
        identity,
        match.group("version"),
        filename,
        base + filename,
        "sha256",
        checksum,
        hosts,
    )


def _urbackup_restore(identity: IsoIdentity) -> ReleaseArtifact:
    if (
        identity.product_id != "urbackup-restore"
        or identity.edition != "restore"
        or identity.architecture != "x86_64"
        or identity.channel != "stable"
        or identity.flavor
        or identity.language
    ):
        raise ProviderError("UrBackup automatic updates support the stable x64 restore ISO only.")
    hosts = {
        "api.github.com",
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    }
    client = SafeHttpClient(frozenset(hosts))
    payload = json.loads(
        _text(client, "https://api.github.com/repos/uroni/urbackup_restore_cd/releases/latest")
    )
    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        raise ProviderError("The official UrBackup release has no asset list.")
    candidates: list[tuple[str, dict[str, object]]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        if isinstance(name, str) and (
            match := re.fullmatch(r"urbackup_restore_(\d+(?:\.\d+)+)\.iso", name, re.I)
        ):
            candidates.append((match.group(1), asset))
    if not candidates:
        raise ProviderError("The official UrBackup release contains no x64 restore ISO.")
    version, selected = max(candidates, key=lambda item: _version_key(item[0]))
    filename = str(selected["name"])
    url = selected.get("browser_download_url")
    digest = selected.get("digest")
    size = selected.get("size")
    if not isinstance(url, str) or not url.endswith("/" + filename):
        raise ProviderError("The UrBackup release URL is not bound to its ISO filename.")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[A-Fa-f0-9]{64}", digest):
        raise ProviderError("The official UrBackup release lacks a SHA-256 asset digest.")
    if not isinstance(size, int) or size <= 0:
        raise ProviderError("The official UrBackup release lacks a valid ISO size.")
    return _artifact(
        identity,
        version,
        filename,
        url,
        "sha256",
        digest.removeprefix("sha256:").lower(),
        hosts,
        size_bytes=size,
    )


def _kali_linux(identity: IsoIdentity) -> ReleaseArtifact:
    editions = {"installer", "installer-netinst", "installer-purple", "live", "live-everything"}
    if identity.edition not in editions or identity.architecture not in {"amd64", "arm64"}:
        raise ProviderError("This Kali image type or architecture is not supported.")
    if identity.flavor or identity.channel != "stable":
        raise ProviderError("Kali automatic updates support quarterly unmodified images only.")
    hosts = {"archive.kali.org", "cdimage.kali.org"}
    base = "https://archive.kali.org/kali-images/current/"
    client = SafeHttpClient(frozenset(hosts))
    sums = _text(client, base + "SHA256SUMS")
    pattern = re.compile(
        rf"\b(kali-linux-(?P<version>\d{{4}}\.\d+)-{re.escape(identity.edition)}-"
        rf"{re.escape(identity.architecture)}\.iso)\b"
    )
    matches = list(pattern.finditer(sums))
    if not matches:
        raise ProviderError("The official Kali checksum list contains no matching ISO.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename, version = match.group(1), match.group("version")
    return _artifact(
        identity,
        version,
        filename,
        base + filename,
        "sha256",
        _checksum(sums, filename, "sha256"),
        hosts,
    )


def _kaos(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.architecture != "x86_64" or identity.channel != "stable":
        raise ProviderError("KaOS automatic updates support stable x86_64 media only.")
    if identity.edition != "dinit":
        raise ProviderError(
            "The historical KaOS systemd image cannot be changed to Dinit automatically."
        )
    hosts = {"kaosx.us", "kaosx-eu.yourhostingsolutions.com"}
    client = SafeHttpClient(frozenset(hosts))
    # The slashless URL currently redirects through plain HTTP before returning to HTTPS.
    # Address the canonical HTTPS path directly so the shared client never weakens transport.
    page = _text(client, "https://kaosx.us/download/")
    expression = re.compile(
        r"(?P<url>https://kaosx-eu\.yourhostingsolutions\.com/"
        r"(?P<filename>KaOS-DINIT-(?P<version>\d{4}\.\d{2})-x86_64\.iso))\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(page))
    if not matches:
        raise ProviderError("The official KaOS page lacks the current Dinit ISO link.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename, version = match.group("filename"), match.group("version")
    digest_match = re.search(
        rf"SHA256SUM\s+KaOS-DINIT\s+{re.escape(version)}.{{0,2000}}?"
        r"(?P<hash>[A-Fa-f0-9]{64})",
        page,
        re.IGNORECASE | re.DOTALL,
    )
    if digest_match is None:
        raise ProviderError("The official KaOS page lacks the selected ISO SHA-256 value.")
    return _artifact(
        identity,
        version,
        filename,
        match.group("url"),
        "sha256",
        digest_match.group("hash").lower(),
        hosts,
    )


def _nixos(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.edition not in {"graphical", "minimal"} or identity.architecture not in {
        "x86_64",
        "aarch64",
    }:
        raise ProviderError("This NixOS image type or architecture is not supported.")
    if identity.flavor not in {None, "plasma5"} or (
        identity.flavor == "plasma5" and identity.edition != "graphical"
    ):
        raise ProviderError("This NixOS graphical flavor cannot be preserved.")
    hosts = {"nixos.org", "channels.nixos.org", "releases.nixos.org"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://nixos.org/download/")
    channels = re.findall(r"nixos-(\d+\.\d+)/latest-nixos", page)
    if not channels:
        release = re.search(r"\b(\d{2}\.\d{2})\b", page)
        channels = [release.group(1)] if release else []
    if not channels:
        raise ProviderError("The official NixOS page contains no stable release channel.")
    channel = max(channels, key=_version_key)
    base = f"https://channels.nixos.org/nixos-{channel}/latest-nixos-{identity.edition}-"
    url = f"{base}{identity.architecture}-linux.iso"
    sums = _text(client, url + ".sha256")
    checksum_match = re.fullmatch(r"\s*(?P<hash>[A-Fa-f0-9]{64})\s+(?P<filename>[^\s]+)\s*", sums)
    if checksum_match is None:
        raise ProviderError("The official NixOS checksum sidecar is invalid.")
    filename = checksum_match.group("filename")
    artifact_match = re.fullmatch(
        rf"nixos-{identity.edition}-(?P<version>\d+\.\d+\.\d+\.[a-f0-9]+)-"
        rf"{identity.architecture}-linux\.iso",
        filename,
    )
    if artifact_match is None:
        raise ProviderError("The NixOS checksum refers to an unexpected artifact.")
    return _artifact(
        identity,
        artifact_match.group("version"),
        filename,
        url,
        "sha256",
        checksum_match.group("hash").lower(),
        hosts,
    )


def _systemrescue(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.edition != "live" or identity.architecture != "amd64" or identity.flavor:
        raise ProviderError("SystemRescue automatic updates support the stable amd64 ISO only.")
    hosts = {"www.system-rescue.org", "fastly-cdn.system-rescue.org"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://www.system-rescue.org/Download/")
    matches = re.findall(r"\b(systemrescue-(\d+(?:\.\d+)+)-amd64\.iso)\b", page)
    if not matches:
        raise ProviderError("The official SystemRescue page contains no amd64 ISO.")
    filename, version = max(matches, key=lambda item: _version_key(item[1]))
    checksum_base = f"https://www.system-rescue.org/releases/{version}/"
    checksum = _checksum(_text(client, checksum_base + filename + ".sha256"), filename, "sha256")
    url = f"https://fastly-cdn.system-rescue.org/releases/{version}/{filename}"
    return _artifact(identity, version, filename, url, "sha256", checksum, hosts)


def _super_grub2_disk(identity: IsoIdentity) -> ReleaseArtifact:
    editions = {"multiarch", "i386_pc", "x86_64_efi", "i386_efi"}
    if (
        identity.product_id != "super-grub2-disk"
        or identity.edition not in editions
        or identity.architecture != "multiarch"
        or identity.channel != "stable"
    ):
        raise ProviderError("This Super Grub2 Disk CD variant is not supported.")
    hosts = {
        "www.supergrubdisk.org",
        "downloads.sourceforge.net",
        "sf-eu-introserv-3.dl.sourceforge.net",
    }
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://www.supergrubdisk.org/")
    expression = re.compile(
        rf"\b(?P<filename>supergrub2-classic-(?P<version>\d+\.\d+s\d+)-"
        rf"{re.escape(identity.edition)}-CD\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(page))
    if not matches:
        raise ProviderError("The official Super Grub2 Disk page lacks this CD variant.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename, version = match.group("filename"), match.group("version")
    checksum = _checksum(page, filename, "sha256")
    url = (
        "https://downloads.sourceforge.net/project/supergrub2/"
        f"{version}/super_grub2_disk_{version}/{filename}"
        "?use_mirror=sf-eu-introserv-3"
    )
    return _artifact(identity, version, filename, url, "sha256", checksum, hosts)


def _nobara(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.flavor == "nvidia":
        raise ProviderError(
            "The historical Nobara Nvidia-specific images were discontinued. Assign this ISO "
            "to a current unified edition explicitly before updating."
        )
    editions = {
        "official": "Official",
        "gnome": "GNOME",
        "kde": "KDE",
        "steam-htpc": "Steam-HTPC",
        "steam-handheld": "Steam-Handheld",
    }
    try:
        edition = editions[identity.edition or ""]
    except KeyError as error:
        raise ProviderError("This Nobara edition is not supported.") from error
    if identity.architecture != "x86_64" or identity.channel != "stable" or identity.flavor:
        raise ProviderError("Nobara automatic updates support stable x86_64 images only.")
    hosts = {"nobaraproject.org", "nobara-images.nobaraproject.org"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://nobaraproject.org/download.html")
    pattern = re.compile(
        rf"Nobara-(?P<version>\d+)-{re.escape(edition)}-"
        r"(?P<build>\d{4}-\d{2}-\d{2})\.iso",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(page))
    if not matches:
        raise ProviderError("The Nobara download page contains no matching ISO edition.")
    match = max(
        matches,
        key=lambda item: (_version_key(item.group("version")), item.group("build")),
    )
    filename = match.group(0)
    url = f"https://nobara-images.nobaraproject.org/{filename}"
    checksum = _checksum(_text(client, url + ".sha256sum"), filename, "sha256")
    return _artifact(
        identity,
        match.group("version"),
        filename,
        url,
        "sha256",
        checksum,
        hosts,
        build=match.group("build"),
    )


def _opensuse_tumbleweed(identity: IsoIdentity) -> ReleaseArtifact:
    editions = {"dvd", "net", "rescue-cd", "gnome-live", "kde-live", "xfce-live"}
    if identity.edition not in editions or identity.architecture not in {"x86_64", "aarch64"}:
        raise ProviderError("This openSUSE Tumbleweed medium or architecture is not supported.")
    host = "download.opensuse.org"
    client = SafeHttpClient(frozenset({host}))
    if identity.architecture == "aarch64":
        base = f"https://{host}/download/ports/aarch64/tumbleweed/iso/"
    else:
        base = f"https://{host}/download/tumbleweed/iso/"
    listing = _text(client, base)
    label = {
        "dvd": "DVD",
        "net": "NET",
        "rescue-cd": "Rescue-CD",
        "gnome-live": "GNOME-Live",
        "kde-live": "KDE-Live",
        "xfce-live": "XFCE-Live",
    }[identity.edition]
    pattern = re.compile(
        rf"\b(openSUSE-Tumbleweed-{label}-{re.escape(identity.architecture)}-"
        rf"Snapshot(?P<version>\d{{8}})-Media\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(listing))
    if not matches:
        raise ProviderError("The openSUSE directory contains no matching snapshot ISO.")
    match = max(matches, key=lambda item: item.group("version"))
    filename, version = match.group(1), match.group("version")
    checksum = _checksum(_text(client, base + filename + ".sha256"), filename, "sha256")
    return _artifact(identity, version, filename, base + filename, "sha256", checksum, {host})


def _opensuse_leap(identity: IsoIdentity) -> ReleaseArtifact:
    host = "download.opensuse.org"
    client = SafeHttpClient(frozenset({host}))
    if identity.channel == "15.6":
        if identity.edition not in {"dvd", "net"} or identity.architecture not in {
            "x86_64",
            "aarch64",
            "ppc64le",
            "s390x",
        }:
            raise ProviderError("This openSUSE Leap 15.6 medium or architecture is unsupported.")
        base = f"https://{host}/distribution/leap/15.6/iso/"
        label = identity.edition.upper()
        filename = f"openSUSE-Leap-15.6-{label}-{identity.architecture}-Media.iso"
        listing = _text(client, base)
        if not re.search(rf"\b{re.escape(filename)}\b", listing, re.IGNORECASE):
            raise ProviderError("The openSUSE Leap 15.6 directory lacks this ISO variant.")
        checksum = _checksum(_text(client, base + filename + ".sha256"), filename, "sha256")
        return _artifact(identity, "15.6", filename, base + filename, "sha256", checksum, {host})
    if identity.channel != "16.0" or identity.edition not in {"offline", "online"}:
        raise ProviderError("This openSUSE Leap channel or installer type is unsupported.")
    supported = {
        "offline": {"x86_64"},
        "online": {"x86_64", "aarch64", "ppc64le", "s390x"},
    }
    if identity.architecture not in supported[identity.edition]:
        raise ProviderError("This openSUSE Leap 16.0 installer architecture is unavailable.")
    base = f"https://{host}/distribution/leap/16.0/offline/"
    expression = re.compile(
        rf"\b(Leap-16\.0-{re.escape(identity.edition)}-installer-"
        rf"{re.escape(identity.architecture)}-Build(?P<build>\d+(?:\.\d+)+)"
        rf"\.install\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(_text(client, base)))
    if not matches:
        raise ProviderError("The openSUSE Leap 16.0 directory lacks this ISO variant.")
    match = max(matches, key=lambda item: _version_key(item.group("build")))
    filename, build = match.group(1), match.group("build")
    checksum = _checksum(_text(client, base + filename + ".sha512"), filename, "sha512")
    return _artifact(
        identity,
        "16.0",
        filename,
        base + filename,
        "sha512",
        checksum,
        {host},
        build=build,
    )


def _freebsd(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.edition not in {"disc1", "dvd1", "bootonly"} or identity.architecture not in {
        "amd64",
        "arm64",
    }:
        raise ProviderError("This FreeBSD medium or architecture is not supported.")
    host = "download.freebsd.org"
    client = SafeHttpClient(frozenset({host}))
    root = f"https://{host}/ftp/releases/ISO-IMAGES/"
    versions = re.findall(r'href=["\'](?P<version>\d+(?:\.\d+)+)/["\']', _text(client, root))
    if not versions:
        raise ProviderError("The FreeBSD release directory contains no releases.")
    version = max(versions, key=_version_key)
    base = f"{root}{version}/"
    filename = f"FreeBSD-{version}-RELEASE-{identity.architecture}-{identity.edition}.iso"
    checksum_name = f"CHECKSUM.SHA256-FreeBSD-{version}-RELEASE-{identity.architecture}"
    checksum = _checksum(_text(client, base + checksum_name), filename, "sha256")
    return _artifact(identity, version, filename, base + filename, "sha256", checksum, {host})


def _openbsd(identity: IsoIdentity) -> ReleaseArtifact:
    architectures = {
        "alpha",
        "amd64",
        "arm64",
        "hppa",
        "i386",
        "loongson",
        "macppc",
        "powerpc64",
        "sparc64",
    }
    if (
        identity.edition not in {"install", "bootonly"}
        or identity.architecture not in architectures
    ):
        raise ProviderError("This OpenBSD medium or architecture is not supported.")
    host = "cdn.openbsd.org"
    client = SafeHttpClient(frozenset({host}))
    root = f"https://{host}/pub/OpenBSD/"
    releases = re.findall(r'href=["\'](?P<version>\d+\.\d+)/["\']', _text(client, root))
    if not releases:
        raise ProviderError("The official OpenBSD directory contains no releases.")
    version = max(releases, key=_version_key)
    compact = version.replace(".", "")
    upstream_name = f"{'install' if identity.edition == 'install' else 'cd'}{compact}.iso"
    base = f"{root}{version}/{identity.architecture}/"
    checksum = _checksum(_text(client, base + "SHA256"), upstream_name, "sha256")
    filename = f"OpenBSD-{version}-{identity.architecture}-{identity.edition}.iso"
    return _artifact(
        identity,
        version,
        filename,
        base + upstream_name,
        "sha256",
        checksum,
        {host},
    )


def _omnios(identity: IsoIdentity) -> ReleaseArtifact:
    if (
        identity.edition != "installer"
        or identity.architecture != "x86_64"
        or identity.channel not in {"stable", "lts", "bloody"}
    ):
        raise ProviderError("This OmniOS medium, architecture or release channel is unsupported.")
    host = "downloads.omnios.org"
    client = SafeHttpClient(frozenset({host}))
    base = f"https://{host}/media/{identity.channel}/"
    if identity.channel == "bloody":
        expression = re.compile(r"\b(omnios-bloody-(?P<version>\d{8})\.iso)\b", re.I)
    else:
        expression = re.compile(r"\b(omnios-r(?P<version>\d+[a-z]?)\.iso)\b", re.I)
    matches = list(expression.finditer(_text(client, base)))
    if not matches:
        raise ProviderError("The selected OmniOS channel contains no installation ISO.")
    match = max(
        matches,
        key=lambda item: (_version_key(item.group("version")), item.group("version").lower()),
    )
    upstream_name, version = match.group(1), match.group("version")
    checksum = _checksum(_text(client, base + upstream_name + ".sha256"), upstream_name, "sha256")
    filename = (
        upstream_name
        if identity.channel == "bloody"
        else f"omnios-{identity.channel}-r{version}.iso"
    )
    return _artifact(
        identity,
        version,
        filename,
        base + upstream_name,
        "sha256",
        checksum,
        {host},
    )


def _tuxedo_os(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.edition != "desktop" or identity.architecture != "x86_64":
        raise ProviderError("TUXEDO OS automatic updates support the x86_64 desktop ISO only.")
    if identity.flavor is not None:
        raise ProviderError("This TUXEDO OS image flavor is unsupported.")
    host = "os.tuxedocomputers.com"
    client = SafeHttpClient(frozenset({host}))
    base = f"https://{host}/"
    names = re.findall(r"\b(TUXEDO-OS-(?P<version>\d{12})\.iso)\b", _text(client, base))
    if not names:
        raise ProviderError("The official TUXEDO OS index contains no versioned ISO.")
    filename, version = max(names, key=lambda item: _version_key(item[1]))
    checksum_url = base + "checksums/" + filename + ".sha256"
    checksum = _checksum(_text(client, checksum_url), filename, "sha256")
    return _artifact(identity, version, filename, base + filename, "sha256", checksum, {host})


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
    return _artifact(identity, version, filename, url, "sha256", checksum, hosts)


def _manjaro(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.edition not in {"gnome", "kde", "xfce"} or identity.architecture != "x86_64":
        raise ProviderError("This Manjaro edition or architecture has no configured official feed.")
    if identity.channel != "stable":
        raise ProviderError("Manjaro review/preview updates require an explicit channel mapping.")
    if identity.flavor not in {"full", "minimal"}:
        raise ProviderError("Manjaro updates require an explicit full or minimal image flavor.")
    hosts = {"download.manjaro.org", "gitlab.manjaro.org"}
    client = SafeHttpClient(frozenset(hosts))
    metadata_url = "https://gitlab.manjaro.org/webpage/iso-info/-/raw/master/file-info.json"
    payload = json.loads(_text(client, metadata_url))
    edition_key = "plasma" if identity.edition == "kde" else identity.edition
    try:
        variant = payload["official"][edition_key]
        if identity.flavor == "minimal":
            variant = variant["minimal"]
        url = str(variant["image"])
        sums_url = str(variant["checksum"])
    except (KeyError, TypeError) as error:
        raise ProviderError(
            "The Manjaro metadata contains no matching full/minimal ISO."
        ) from error
    filename = url.rsplit("/", 1)[-1]
    expected = re.fullmatch(
        rf"manjaro-{re.escape(identity.edition)}-(?P<version>\d+(?:\.\d+)+)"
        rf"{'-minimal' if identity.flavor == 'minimal' else ''}"
        r"-(?P<build>\d{6})-linux\d+\.iso",
        filename,
    )
    if expected is None or sums_url != url + ".sha256":
        raise ProviderError("The Manjaro metadata returned invalid artifact paths.")
    version = expected.group("version")
    build = expected.group("build")
    sums = _text(client, sums_url)
    return _artifact(
        identity,
        version,
        filename,
        url,
        "sha256",
        _checksum(sums, filename, "sha256"),
        hosts,
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
        identity,
        str(payload.get("version", version)),
        filename,
        url,
        "sha256",
        checksum.lower(),
        hosts,
        build=str(payload.get("build")),
        size_bytes=int(payload["size"]),
    )


def _proxmox(identity: IsoIdentity) -> ReleaseArtifact:
    prefixes = {
        "proxmox-ve": "proxmox-ve",
        "proxmox-backup-server": "proxmox-backup-server",
        "proxmox-mail-gateway": "proxmox-mail-gateway",
        "proxmox-datacenter-manager": "proxmox-datacenter-manager",
    }
    try:
        prefix = prefixes[identity.product_id]
    except KeyError as error:
        raise ProviderError("This Proxmox product is not supported.") from error
    if identity.edition != "installer" or identity.architecture not in {"amd64", "arm64"}:
        raise ProviderError("This Proxmox installer variant is not supported.")
    if identity.architecture == "arm64" and identity.product_id != "proxmox-ve":
        raise ProviderError("Only Proxmox VE currently publishes an ARM64 ISO.")
    host = "enterprise.proxmox.com"
    client = SafeHttpClient(frozenset({host}))
    page = _text(client, f"https://{host}/iso/")
    arch_suffix = "-arm64" if identity.architecture == "arm64" else ""
    pattern = re.compile(
        rf"\b({re.escape(prefix)}_(?P<version>\d+(?:\.\d+)+-\d+){arch_suffix}\.iso)\b"
    )
    matches = list(pattern.finditer(page))
    if not matches:
        raise ProviderError("The official Proxmox index contains no matching ISO.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename, version = match.group(1), match.group("version")
    return _artifact(
        identity,
        version,
        filename,
        f"https://{host}/iso/{filename}",
        "sha256",
        _checksum(page, filename, "sha256"),
        {host},
    )


def _rescuezilla(identity: IsoIdentity) -> ReleaseArtifact:
    if (
        identity.edition != "live"
        or identity.flavor not in {"noble", "oracular", "questing", "resolute"}
        or identity.architecture != "amd64"
    ):
        raise ProviderError("This Rescuezilla image variant is not supported.")
    hosts = {
        "api.github.com",
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    }
    client = SafeHttpClient(frozenset(hosts))
    payload = json.loads(
        _text(client, "https://api.github.com/repos/rescuezilla/rescuezilla/releases/latest")
    )
    version = str(payload.get("tag_name", "")).removeprefix("v")
    filename = f"rescuezilla-{version}-64bit.{identity.flavor}.iso"
    assets = {
        str(asset.get("name")): asset
        for asset in payload.get("assets", [])
        if isinstance(asset, dict)
    }
    asset = assets.get(filename)
    if not version or asset is None:
        raise ProviderError("The Rescuezilla release lacks the selected Ubuntu-base variant.")
    digest = str(asset.get("digest", ""))
    if not re.fullmatch(r"sha256:[A-Fa-f0-9]{64}", digest):
        raise ProviderError("The Rescuezilla asset lacks an official SHA-256 digest.")
    return _artifact(
        identity,
        version,
        filename,
        str(asset.get("browser_download_url", "")),
        "sha256",
        digest.removeprefix("sha256:").lower(),
        hosts,
        size_bytes=int(asset["size"]),
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
        identity,
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
    url = f"https://zrn.co/{version.split('.', 1)[0]}{edition.lower()}64"
    return _artifact(
        identity,
        version,
        filename,
        url,
        "sha256",
        match.group("hash").lower(),
        hosts,
        build=build,
    )


def _netboot_xyz(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "netboot-xyz" or identity.edition not in {"standard", "legacy"}:
        raise ProviderError("This netboot.xyz ISO variant is not supported.")
    if identity.architecture not in {"x86_64", "arm64"}:
        raise ProviderError("This netboot.xyz architecture is not supported.")
    if identity.edition == "legacy" and identity.architecture != "x86_64":
        raise ProviderError("The legacy netboot.xyz ISO is published for x86_64 only.")
    hosts = {
        "api.github.com",
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    }
    client = SafeHttpClient(frozenset(hosts))
    payload = json.loads(
        _text(client, "https://api.github.com/repos/netbootxyz/netboot.xyz/releases/latest")
    )
    version = str(payload.get("tag_name", "")).removeprefix("v")
    if identity.architecture == "arm64":
        filename = "netboot.xyz-arm64.iso"
    elif identity.edition == "legacy":
        filename = "netboot.xyz-legacy.iso"
    else:
        filename = "netboot.xyz.iso"
    assets = {
        str(asset.get("name")): asset
        for asset in payload.get("assets", [])
        if isinstance(asset, dict)
    }
    asset = assets.get(filename)
    if not version or asset is None:
        raise ProviderError("The netboot.xyz release lacks the selected ISO asset.")
    digest = str(asset.get("digest", ""))
    if not re.fullmatch(r"sha256:[A-Fa-f0-9]{64}", digest):
        raise ProviderError("The netboot.xyz ISO lacks an official SHA-256 digest.")
    return _artifact(
        identity,
        version,
        filename,
        str(asset.get("browser_download_url", "")),
        "sha256",
        digest.removeprefix("sha256:").lower(),
        hosts,
        size_bytes=int(asset["size"]),
    )


def _gentoo(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "gentoo" or identity.edition not in {"minimal", "livegui"}:
        raise ProviderError("This Gentoo ISO variant is not supported.")
    if identity.architecture not in {"amd64", "arm64", "x86"}:
        raise ProviderError("This Gentoo architecture is not supported.")
    if identity.edition == "livegui" and identity.architecture != "amd64":
        raise ProviderError("Gentoo LiveGUI is published for amd64 only.")
    host = "distfiles.gentoo.org"
    if identity.edition == "livegui":
        directory = "current-livegui-amd64"
        prefix = "livegui-amd64"
    else:
        directory = f"current-install-{identity.architecture}-minimal"
        prefix = f"install-{identity.architecture}-minimal"
    base = f"https://{host}/releases/{identity.architecture}/autobuilds/{directory}/"
    client = SafeHttpClient(frozenset({host}))
    listing = _text(client, base)
    pattern = re.compile(rf"\b({re.escape(prefix)}-(?P<version>\d{{8}}T\d{{6}}Z)\.iso)\b")
    matches = list(pattern.finditer(listing))
    if not matches:
        raise ProviderError("The Gentoo autobuild directory contains no matching ISO.")
    match = max(matches, key=lambda item: item.group("version"))
    filename, version = match.group(1), match.group("version")
    checksum = _checksum(_text(client, base + filename + ".sha256"), filename, "sha256")
    return _artifact(
        identity,
        version,
        filename,
        base + filename,
        "sha256",
        checksum,
        {host},
    )


def _hirens_bootcd_pe(identity: IsoIdentity) -> ReleaseArtifact:
    if (
        identity.product_id != "hirens-bootcd-pe"
        or identity.edition != "pe"
        or identity.architecture != "x86_64"
    ):
        raise ProviderError("Only the official Hiren's BootCD PE x64 ISO is supported.")
    host = "www.hirensbootcd.org"
    client = SafeHttpClient(frozenset({host}))
    page = _text(client, "https://www.hirensbootcd.org/download/")
    version_match = re.search(
        r"Hiren(?:'|’|&#(?:0?39|8217);)s BootCD PE x64 "
        r"\(v(?P<version>\d+(?:\.\d+)+)\)",
        page,
    )
    checksum_match = re.search(
        r"ISO SHA-256.{0,500}?(?P<hash>[A-Fa-f0-9]{64})", page, re.IGNORECASE | re.DOTALL
    )
    size_match = re.search(r"\((?P<size>\d{7,}) bytes\)", page)
    if version_match is None or checksum_match is None or size_match is None:
        raise ProviderError("The Hiren's BootCD page lacks version, size or SHA-256 metadata.")
    filename = "HBCD_PE_x64.iso"
    return _artifact(
        identity,
        version_match.group("version"),
        filename,
        f"https://{host}/files/{filename}",
        "sha256",
        checksum_match.group("hash").lower(),
        {host},
        size_bytes=int(size_match.group("size")),
    )


def _shredos(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "shredos" or identity.edition not in {"standard", "lite"}:
        raise ProviderError("This ShredOS edition is not supported.")
    if identity.architecture not in {"x86_64", "i686"}:
        raise ProviderError("This ShredOS architecture is not supported.")
    if identity.flavor not in {None, "plus-partition"}:
        raise ProviderError("This ShredOS image flavor is not supported.")
    hosts = {
        "api.github.com",
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    }
    client = SafeHttpClient(frozenset(hosts))
    payload = json.loads(
        _text(client, "https://api.github.com/repos/PartialVolume/shredos.x86_64/releases/latest")
    )
    expression = re.compile(
        r"^shredos-(?P<version>\d{4}\.\d+_\d+)_"
        r"(?P<architecture>x86-64|i686)_v(?P<build>\d+(?:\.\d+)+_\d{8})"
        r"(?P<lite>_lite)?(?P<partition>_plus-partition)?\.iso$",
        re.IGNORECASE,
    )
    selected: tuple[dict[str, object], re.Match[str]] | None = None
    for value in payload.get("assets", []):
        if not isinstance(value, dict):
            continue
        match = expression.fullmatch(str(value.get("name", "")))
        if match is None:
            continue
        architecture = "x86_64" if match.group("architecture").lower() == "x86-64" else "i686"
        edition = "lite" if match.group("lite") else "standard"
        flavor = "plus-partition" if match.group("partition") else None
        if (architecture, edition, flavor) == (
            identity.architecture,
            identity.edition,
            identity.flavor,
        ):
            selected = value, match
            break
    if selected is None:
        raise ProviderError("The latest ShredOS release lacks the selected ISO variant.")
    asset, match = selected
    digest = str(asset.get("digest", ""))
    if not re.fullmatch(r"sha256:[A-Fa-f0-9]{64}", digest):
        raise ProviderError("The ShredOS ISO lacks an official SHA-256 digest.")
    size = asset.get("size")
    if not isinstance(size, int) or size <= 0:
        raise ProviderError("The ShredOS ISO lacks an official download size.")
    return _artifact(
        identity,
        match.group("version"),
        match.group(0),
        str(asset.get("browser_download_url", "")),
        "sha256",
        digest.removeprefix("sha256:").lower(),
        hosts,
        size_bytes=size,
        build=match.group("build"),
    )


def _netbsd(identity: IsoIdentity) -> ReleaseArtifact:
    if (
        identity.product_id != "netbsd"
        or identity.edition != "installer"
        or identity.channel != "release"
    ):
        raise ProviderError("Only NetBSD release installer ISOs are supported.")
    if identity.architecture not in {"amd64", "i386"}:
        raise ProviderError("This NetBSD architecture is not supported.")
    host = "cdn.netbsd.org"
    client = SafeHttpClient(frozenset({host}))
    root = f"https://{host}/pub/NetBSD/"
    listing = _text(client, root)
    versions = set(re.findall(r'href="NetBSD-(\d+(?:\.\d+)+)/"', listing, re.IGNORECASE))
    if not versions:
        raise ProviderError("The official NetBSD directory contains no stable release.")
    version = max(versions, key=lambda value: tuple(int(part) for part in value.split(".")))
    filename = f"NetBSD-{version}-{identity.architecture}.iso"
    base = f"{root}NetBSD-{version}/images/"
    checksum = _checksum(_text(client, base + "SHA512"), filename, "sha512")
    return _artifact(
        identity,
        version,
        filename,
        base + filename,
        "sha512",
        checksum,
        {host},
    )


def _openindiana(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "openindiana" or identity.edition not in {
        "gui",
        "text",
        "minimal",
    }:
        raise ProviderError("This OpenIndiana installer edition is not supported.")
    if identity.architecture != "x86_64" or identity.channel != "rolling":
        raise ProviderError("OpenIndiana automatic updates support rolling x86_64 ISOs only.")
    hosts = {"www.openindiana.org", "dlc.openindiana.org"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://www.openindiana.org/downloads/")
    expression = re.compile(
        r"(?:https:)?//dlc\.openindiana\.org/isos/hipster/"
        r"(?P<version>\d{8})/"
        rf"(?P<filename>OI-hipster-{re.escape(identity.edition)}-"
        r"(?P=version)\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(page))
    if not matches:
        raise ProviderError("The official OpenIndiana page lacks the selected ISO edition.")
    match = max(matches, key=lambda item: item.group("version"))
    filename, url = match.group("filename"), match.group(0)
    if url.startswith("//"):
        url = "https:" + url
    checksum = _checksum(_text(client, url + ".sha256sum"), filename, "sha256")
    return _artifact(
        identity,
        match.group("version"),
        filename,
        url,
        "sha256",
        checksum,
        hosts,
    )


def _xcp_ng(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "xcp-ng" or identity.edition not in {"full", "netinstall"}:
        raise ProviderError("This XCP-ng installer edition is not supported.")
    if identity.architecture != "x86_64" or identity.channel != "lts":
        raise ProviderError("XCP-ng automatic updates support LTS x86_64 ISOs only.")
    host = "updates.xcp-ng.org"
    client = SafeHttpClient(frozenset({host}))
    root = f"https://{host}/isos/"
    listing = _text(client, root)
    series = set(re.findall(r'href=["\'](?P<series>\d+\.\d+)/["\']', listing, re.I))
    if not series:
        raise ProviderError("The official XCP-ng directory contains no release series.")
    current = max(series, key=_version_key)
    base = f"{root}{current}/"
    sums = _text(client, base + "SHA256SUMS")
    expression = re.compile(
        r"\b(xcp-ng-(?P<version>\d+(?:\.\d+){2})-"
        r"(?P<build>\d{8}(?:\.\d+)?)"
        r"(?P<netinstall>-netinstall)?\.iso)\b",
        re.IGNORECASE,
    )
    matches = [
        match
        for match in expression.finditer(sums)
        if (match.group("netinstall") is not None) == (identity.edition == "netinstall")
    ]
    if not matches:
        raise ProviderError("The official XCP-ng checksum list lacks this installer edition.")
    match = max(
        matches,
        key=lambda item: (_version_key(item.group("version")), _version_key(item.group("build"))),
    )
    filename = match.group(1)
    return _artifact(
        identity,
        match.group("version"),
        filename,
        base + filename,
        "sha256",
        _checksum(sums, filename, "sha256"),
        {host},
        build=match.group("build"),
    )


def _porteux(identity: IsoIdentity) -> ReleaseArtifact:
    editions = {"cinnamon", "cosmic", "gnome", "kde", "lxde", "lxqt", "mate", "xfce"}
    if identity.product_id != "porteux" or identity.edition not in editions:
        raise ProviderError("This PorteuX desktop edition is not supported.")
    if identity.architecture != "x86_64" or identity.channel != "current":
        raise ProviderError("PorteuX automatic updates currently support current x86_64 images.")
    hosts = {
        "api.github.com",
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    }
    client = SafeHttpClient(frozenset(hosts))
    payload = json.loads(
        _text(client, "https://api.github.com/repos/porteux/porteux/releases/latest")
    )
    expression = re.compile(
        rf"^porteux-(?P<version>\d+(?:\.\d+)+)-current-"
        rf"{re.escape(identity.edition)}-(?P<build>[A-Za-z0-9.]+)-x86_64\.iso$",
        re.IGNORECASE,
    )
    for value in payload.get("assets", []):
        if not isinstance(value, dict):
            continue
        match = expression.fullmatch(str(value.get("name", "")))
        if match is None:
            continue
        digest = str(value.get("digest", ""))
        size = value.get("size")
        if not re.fullmatch(r"sha256:[A-Fa-f0-9]{64}", digest):
            raise ProviderError("The PorteuX ISO lacks an official SHA-256 digest.")
        if not isinstance(size, int) or size <= 0:
            raise ProviderError("The PorteuX ISO lacks an official download size.")
        return _artifact(
            identity,
            match.group("version"),
            match.group(0),
            str(value.get("browser_download_url", "")),
            "sha256",
            digest.removeprefix("sha256:").lower(),
            hosts,
            size_bytes=size,
            build=match.group("build"),
        )
    raise ProviderError("The latest PorteuX release lacks the selected desktop ISO.")


def _ghostbsd(identity: IsoIdentity) -> ReleaseArtifact:
    channels = {"mate": "official", "xfce": "community", "gershwin": "preview"}
    if identity.product_id != "ghostbsd" or identity.edition not in channels:
        raise ProviderError("This GhostBSD desktop image is not supported.")
    if identity.architecture != "amd64" or identity.channel != channels[identity.edition]:
        raise ProviderError("The GhostBSD desktop edition and update channel do not match.")
    hosts = {"www.ghostbsd.org", "download.ghostbsd.org"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://www.ghostbsd.org/download")
    suffix = {"mate": "", "xfce": "-XFCE", "gershwin": "-GERSHWIN"}[identity.edition]
    expression = re.compile(
        r"https://download\.ghostbsd\.org/releases/amd64/"
        r"(?P<version>\d+(?:\.\d+)+-R\d+(?:\.\d+)+p\d+)/"
        rf"(?P<filename>GhostBSD-(?P=version){suffix}\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(page))
    if not matches:
        raise ProviderError("The official GhostBSD page lacks the selected ISO.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename = match.group("filename")
    url = match.group(0)
    checksum = _checksum(_text(client, url + ".sha256"), filename, "sha256")
    return _artifact(
        identity,
        match.group("version"),
        filename,
        url,
        "sha256",
        checksum,
        hosts,
    )


def _haiku(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "haiku" or identity.edition != "anyboot":
        raise ProviderError("Only official Haiku anyboot ISOs are supported.")
    if identity.architecture not in {"x86_64", "x86_gcc2h"} or identity.channel != "stable":
        raise ProviderError("This Haiku architecture or release channel is not supported.")
    hosts = {"www.haiku-os.org", "haiku-release.cdn.haiku-os.org"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://www.haiku-os.org/get-haiku/")
    expression = re.compile(
        rf"\b(haiku-(?P<version>r\d+beta\d+)-{re.escape(identity.architecture)}-"
        rf"anyboot\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(page))
    if not matches:
        raise ProviderError("The official Haiku page lacks the selected anyboot ISO.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename, version = match.group(1), match.group("version").lower()
    checksum = _checksum(page, filename, "sha256")
    url = f"https://haiku-release.cdn.haiku-os.org/{version}/{filename}"
    return _artifact(identity, version, filename, url, "sha256", checksum, hosts)


def _harvester(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "harvester" or identity.edition not in {"full", "netinstall"}:
        raise ProviderError("This Harvester installer medium is not supported.")
    if identity.architecture not in {"amd64", "arm64"} or identity.channel != "stable":
        raise ProviderError("This Harvester architecture or release channel is unsupported.")
    if identity.edition == "netinstall" and identity.architecture != "amd64":
        raise ProviderError("Harvester net-install media are published for AMD64 only.")
    hosts = {"api.github.com", "github.com", "releases.rancher.com"}
    client = SafeHttpClient(frozenset(hosts))
    payload = json.loads(
        _text(client, "https://api.github.com/repos/harvester/harvester/releases?per_page=100")
    )
    if not isinstance(payload, list):
        raise ProviderError("The official Harvester release feed is invalid.")
    releases: list[tuple[str, str]] = []
    for release in payload:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        tag = str(release.get("tag_name", ""))
        if not re.fullmatch(r"v\d+(?:\.\d+)+", tag):
            continue
        releases.append((tag.removeprefix("v"), str(release.get("body", ""))))
    if not releases:
        raise ProviderError("The official Harvester feed contains no stable release.")
    version, body = max(releases, key=lambda item: _version_key(item[0]))
    suffix = "-net-install" if identity.edition == "netinstall" else ""
    filename = f"harvester-v{version}-{identity.architecture}{suffix}.iso"
    base = f"https://releases.rancher.com/harvester/v{version}/"
    url = base + filename
    sums_url = base + f"harvester-v{version}-{identity.architecture}.sha512"
    if url not in body or sums_url not in body:
        raise ProviderError("The Harvester release notes lack this ISO or checksum link.")
    sums = _text(client, sums_url)
    return _artifact(
        identity,
        version,
        filename,
        url,
        "sha512",
        _checksum(sums, filename, "sha512"),
        hosts,
    )


def _solus(identity: IsoIdentity) -> ReleaseArtifact:
    editions = {"budgie": "Budgie", "gnome": "GNOME", "plasma": "Plasma", "xfce": "Xfce"}
    if identity.product_id != "solus" or identity.edition not in editions:
        raise ProviderError("This Solus desktop edition is not supported.")
    if identity.architecture != "x86_64" or identity.channel != "stable":
        raise ProviderError("Solus automatic updates support stable x86_64 images only.")
    hosts = {"getsol.us", "downloads.getsol.us"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://getsol.us/download/")
    name = editions[identity.edition]
    expression = re.compile(
        rf"https://downloads\.getsol\.us/isos/(?P<version>\d{{4}}-\d{{2}}-\d{{2}})/"
        rf"(?P<filename>Solus-{name}-Release-(?P=version)\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(page))
    if not matches:
        raise ProviderError("The official Solus page lacks the selected desktop ISO.")
    match = max(matches, key=lambda item: item.group("version"))
    filename, url = match.group("filename"), match.group(0)
    checksum = _checksum(_text(client, url + ".sha256sum"), filename, "sha256")
    return _artifact(
        identity,
        match.group("version"),
        filename,
        url,
        "sha256",
        checksum,
        hosts,
    )


def _truenas(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "truenas" or identity.edition != "community":
        raise ProviderError("Only TrueNAS Community Edition installers are supported.")
    if identity.architecture != "x86_64" or identity.channel not in {"stable", "beta"}:
        raise ProviderError("This TrueNAS architecture or channel is not supported.")
    hosts = {
        "www.truenas.com",
        "download.sys.truenas.net",
        "iso.sys.truenas.net",
    }
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://www.truenas.com/download-truenas-community-edition/")
    if identity.channel == "stable":
        expression = re.compile(
            r"https://download\.sys\.truenas\.net/[^\s\"'<>]+/"
            r"(?P<version>\d+(?:\.\d+)+)/"
            r"(?P<filename>TrueNAS-SCALE-(?P=version)\.iso)\b",
            re.IGNORECASE,
        )
    else:
        expression = re.compile(
            r"https://iso\.sys\.truenas\.net/[^\s\"'<>]+/"
            r"(?P<version>\d+(?:\.\d+)+-BETA\.\d+)/"
            r"(?P<filename>TrueNAS-(?P=version)\.iso)\b",
            re.IGNORECASE,
        )
    matches = list(expression.finditer(page))
    if not matches:
        raise ProviderError("The official TrueNAS page lacks the selected installer channel.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename, url = match.group("filename"), match.group(0)
    checksum = _checksum(_text(client, url + ".sha256"), filename, "sha256")
    return _artifact(
        identity,
        match.group("version"),
        filename,
        url,
        "sha256",
        checksum,
        hosts,
    )


def _tails(identity: IsoIdentity) -> ReleaseArtifact:
    if (
        identity.product_id != "tails"
        or identity.edition != "iso"
        or identity.architecture != "amd64"
        or identity.channel != "stable"
    ):
        raise ProviderError("Only the official stable Tails amd64 ISO is supported.")
    hosts = {
        "tails.net",
        "download.tails.net",
        "mirror.bouwhuis.network",
        "ftp.fau.de",
        "tails.hivane.net",
        "tails.ybti.net",
        "mirror.netcologne.de",
    }
    client = SafeHttpClient(frozenset(hosts))
    metadata_url = "https://tails.net/install/v2/Tails/amd64/stable/latest.json"
    payload = json.loads(_text(client, metadata_url))
    installations = payload.get("installations", [])
    if not isinstance(installations, list):
        raise ProviderError("The official Tails metadata has no installation list.")
    candidates: list[tuple[str, dict[str, object]]] = []
    for installation in installations:
        if not isinstance(installation, dict):
            continue
        version = installation.get("version")
        paths = installation.get("installation-paths", [])
        if not isinstance(version, str) or not isinstance(paths, list):
            continue
        for path in paths:
            if not isinstance(path, dict) or path.get("type") != "iso":
                continue
            files = path.get("target-files", [])
            if isinstance(files, list):
                candidates.extend((version, item) for item in files if isinstance(item, dict))
    if not candidates:
        raise ProviderError("The official Tails metadata contains no stable ISO.")
    version, selected = max(candidates, key=lambda item: _version_key(item[0]))
    filename = f"tails-amd64-{version}.iso"
    url = str(selected.get("url", ""))
    digest = str(selected.get("sha256", ""))
    size = selected.get("size")
    if not url.endswith("/" + filename) or not re.fullmatch(r"[A-Fa-f0-9]{64}", digest):
        raise ProviderError("The Tails ISO metadata is not bound to the expected artifact.")
    if not isinstance(size, int) or size <= 0:
        raise ProviderError("The Tails ISO metadata lacks a valid download size.")
    return _artifact(
        identity,
        version,
        filename,
        url,
        "sha256",
        digest.lower(),
        hosts,
        size_bytes=size,
    )


def _grml(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "grml" or identity.edition not in {"full", "small"}:
        raise ProviderError("This Grml image edition is not supported.")
    if identity.architecture not in {"amd64", "arm64"} or identity.channel != "stable":
        raise ProviderError("This Grml architecture or channel is not supported.")
    hosts = {"grml.org", "ftp-master.grml.org"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://grml.org/download/")
    expression = re.compile(
        rf"\b(grml-{re.escape(identity.edition)}-(?P<version>\d{{4}}\.\d{{2}})-"
        rf"{re.escape(identity.architecture)}\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(page))
    if not matches:
        raise ProviderError("The official Grml page lacks the selected stable ISO.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename, version = match.group(1), match.group("version")
    url = f"https://ftp-master.grml.org/{filename}"
    checksum = _checksum(_text(client, url + ".sha256"), filename, "sha256")
    return _artifact(identity, version, filename, url, "sha256", checksum, hosts)


def _kde_neon(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "kde-neon" or identity.edition != "desktop":
        raise ProviderError("Only KDE neon desktop ISOs are supported.")
    if identity.architecture != "x86_64" or identity.channel not in {
        "user",
        "testing",
        "unstable",
    }:
        raise ProviderError("This KDE neon architecture or channel is not supported.")
    hosts = {"files.kde.org", "ftp.gwdg.de"}
    client = SafeHttpClient(frozenset(hosts))
    base = f"https://files.kde.org/neon/images/desktop/{identity.channel}/current/"
    listing = _text(client, base)
    expression = re.compile(
        rf"\b(neon-{re.escape(identity.channel)}-desktop-"
        rf"(?P<version>\d{{8}}-\d{{4}})\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(listing))
    if not matches:
        raise ProviderError("The KDE neon current directory lacks the selected channel ISO.")
    match = max(matches, key=lambda item: item.group("version"))
    filename, version = match.group(1), match.group("version")
    mirror_base = (
        "https://ftp.gwdg.de/pub/linux/kde/extrafiles/neon/images/desktop/"
        f"{identity.channel}/{version}/"
    )
    checksum_name = filename.removesuffix(".iso") + ".sha256sum"
    checksum = _checksum(_text(client, mirror_base + checksum_name), filename, "sha256")
    return _artifact(
        identity,
        version,
        filename,
        mirror_base + filename,
        "sha256",
        checksum,
        hosts,
    )


def _parrot_os(identity: IsoIdentity) -> ReleaseArtifact:
    editions = {"home", "security", "enlightenment", "htb", "lxqt", "mate"}
    if identity.product_id != "parrot-os" or identity.edition not in editions:
        raise ProviderError("This Parrot OS edition is not supported.")
    if identity.architecture != "amd64" or identity.channel != "stable":
        raise ProviderError("Parrot OS automatic updates support stable amd64 ISOs only.")
    hosts = {"deb.parrot.sh"}
    client = SafeHttpClient(frozenset(hosts))
    root = "https://deb.parrot.sh/parrot/iso/"
    listing = _text(client, root)
    versions = re.findall(r'href=["\'](?P<version>\d+\.\d+)/["\']', listing, re.IGNORECASE)
    if not versions:
        raise ProviderError("The official Parrot OS directory contains no releases.")
    version = max(versions, key=_version_key)
    prefix = "Parrot" if identity.edition in {"home", "security"} else "Parrot-spin"
    filename = f"{prefix}-{identity.edition}-{version}_amd64.iso"
    base = f"{root}{version}/"
    hashes = _text(client, base + "signed-hashes.txt")
    checksum = _checksum(hashes, filename, "sha512")
    return _artifact(
        identity,
        version,
        filename,
        base + filename,
        "sha512",
        checksum,
        hosts,
    )


def _void_linux(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "void-linux" or identity.edition not in {"base", "xfce"}:
        raise ProviderError("This Void Linux image type is not supported.")
    if identity.flavor not in {"glibc", "musl"} or identity.architecture not in {
        "x86_64",
        "i686",
        "aarch64",
        "asahi",
    }:
        raise ProviderError("This Void Linux libc or architecture is not supported.")
    if identity.channel != "stable" or (
        identity.architecture == "i686" and identity.flavor == "musl"
    ):
        raise ProviderError("This Void Linux image combination is not published.")
    hosts = {"repo-default.voidlinux.org"}
    client = SafeHttpClient(frozenset(hosts))
    base = "https://repo-default.voidlinux.org/live/current/"
    sums = _text(client, base + "sha256sum.txt")
    libc = "-musl" if identity.flavor == "musl" else ""
    expression = re.compile(
        rf"\b(void-live-{re.escape(identity.architecture)}{libc}-"
        rf"(?P<version>\d{{8}})-{re.escape(identity.edition)}\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(sums))
    if not matches:
        raise ProviderError("The Void Linux checksum list lacks the selected ISO variant.")
    match = max(matches, key=lambda item: item.group("version"))
    filename, version = match.group(1), match.group("version")
    return _artifact(
        identity,
        version,
        filename,
        base + filename,
        "sha256",
        _checksum(sums, filename, "sha256"),
        hosts,
    )


def _mageia(identity: IsoIdentity) -> ReleaseArtifact:
    editions = {"classic", "gnome", "plasma", "xfce"}
    if identity.product_id != "mageia" or identity.edition not in editions:
        raise ProviderError("This Mageia image type is not supported.")
    if identity.architecture not in {"x86_64", "i686"} or identity.channel != "stable":
        raise ProviderError("This Mageia architecture or channel is not supported.")
    if identity.edition in {"gnome", "plasma"} and identity.architecture != "x86_64":
        raise ProviderError("This Mageia live desktop is published for x86_64 only.")
    host = "mirrors.kernel.org"
    client = SafeHttpClient(frozenset({host}))
    root = f"https://{host}/mageia/iso/"
    versions = re.findall(r'href=["\'](?P<version>\d+)/["\']', _text(client, root))
    if not versions:
        raise ProviderError("The official Mageia mirror contains no releases.")
    version = str(max(map(int, versions)))
    if identity.edition == "classic":
        filename = f"Mageia-{version}-{identity.architecture}.iso"
    else:
        desktop = {"gnome": "GNOME", "plasma": "Plasma", "xfce": "Xfce"}[identity.edition]
        filename = f"Mageia-{version}-Live-{desktop}-{identity.architecture}.iso"
    base = f"{root}{version}/{filename.removesuffix('.iso')}/"
    checksum = _checksum(_text(client, base + filename + ".sha512"), filename, "sha512")
    return _artifact(
        identity,
        version,
        filename,
        base + filename,
        "sha512",
        checksum,
        {host},
    )


def _centos_stream(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "centos-stream" or identity.edition not in {"boot", "dvd1"}:
        raise ProviderError("This CentOS Stream image type is not supported.")
    if identity.channel not in {"9", "10"} or identity.architecture not in {
        "x86_64",
        "aarch64",
    }:
        raise ProviderError("This CentOS Stream release or architecture is not supported.")
    host = "mirror.stream.centos.org"
    client = SafeHttpClient(frozenset({host}))
    base = f"https://{host}/{identity.channel}-stream/BaseOS/{identity.architecture}/iso/"
    sums = _text(client, base + "SHA256SUM")
    expression = re.compile(
        rf"\b(CentOS-Stream-{re.escape(identity.channel)}-"
        rf"(?P<version>\d{{8}}\.\d+)-{re.escape(identity.architecture)}-"
        rf"{re.escape(identity.edition)}\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(sums))
    if not matches:
        raise ProviderError("The CentOS Stream checksum list lacks the selected ISO variant.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename, version = match.group(1), match.group("version")
    return _artifact(
        identity,
        version,
        filename,
        base + filename,
        "sha256",
        _checksum(sums, filename, "sha256"),
        {host},
    )


def _bunsenlabs(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "bunsenlabs" or identity.edition != "desktop":
        raise ProviderError("This BunsenLabs edition is not supported.")
    if identity.architecture != "amd64" or identity.channel != "stable":
        raise ProviderError("BunsenLabs automatic updates support stable AMD64 media only.")
    hosts = {"www.bunsenlabs.org", "ddl.bunsenlabs.org"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://www.bunsenlabs.org/installation.html")
    matches = list(
        re.finditer(
            r"\b(?P<filename>[a-z]+-(?P<version>\d+)-(?P<build>\d{6})-"
            r"amd64\.hybrid\.iso)\b",
            page,
            re.IGNORECASE,
        )
    )
    if not matches:
        raise ProviderError("The official BunsenLabs page contains no stable AMD64 ISO.")
    match = max(
        matches,
        key=lambda item: (_version_key(item.group("version")), item.group("build")),
    )
    filename = match.group("filename")
    version = match.group("version")
    build = match.group("build")
    base = "https://ddl.bunsenlabs.org/ddl/"
    sums = _text(client, base + "release.sha256.txt")
    return _artifact(
        identity,
        version,
        filename,
        base + filename,
        "sha256",
        _checksum(sums, filename, "sha256"),
        hosts,
        build=build,
    )


def _security_onion(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "security-onion" or identity.edition != "installer":
        raise ProviderError("This Security Onion medium is not supported.")
    if identity.architecture != "x86_64" or identity.channel != "stable":
        raise ProviderError("Security Onion automatic updates support stable x86_64 ISOs only.")
    hosts = {"raw.githubusercontent.com", "download.securityonion.net"}
    client = SafeHttpClient(frozenset(hosts))
    metadata = _text(
        client,
        "https://raw.githubusercontent.com/Security-Onion-Solutions/"
        "securityonion/3/main/DOWNLOAD_AND_VERIFY_ISO.md",
    )
    matches = list(
        re.finditer(
            r"https://download\.securityonion\.net/file/securityonion/"
            r"(?P<filename>securityonion-(?P<version>\d+(?:\.\d+)+)-"
            r"(?P<build>\d{8})\.iso)",
            metadata,
            re.IGNORECASE,
        )
    )
    if not matches:
        raise ProviderError("The official Security Onion metadata contains no stable ISO.")
    match = max(
        matches,
        key=lambda item: (_version_key(item.group("version")), item.group("build")),
    )
    filename = match.group("filename")
    version = match.group("version")
    build = match.group("build")
    # The official document lists every digest after the matching ISO URL. Limit
    # the search to that release's nearby section so a stale checksum elsewhere
    # in the document can never be paired with the selected artifact.
    release_section = metadata[match.end() : match.end() + 1_000]
    checksum_match = re.search(
        r"\bSHA256:\s*(?P<hash>[A-Fa-f0-9]{64})\b",
        release_section,
        re.IGNORECASE,
    )
    if checksum_match is None:
        raise ProviderError("The official Security Onion metadata lacks its SHA-256 checksum.")
    return _artifact(
        identity,
        version,
        filename,
        match.group(0),
        "sha256",
        checksum_match.group("hash").lower(),
        hosts,
        build=build,
    )


def _talos_linux(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "talos-linux" or identity.edition != "metal":
        raise ProviderError("This Talos Linux medium is not supported.")
    if identity.architecture not in {"amd64", "arm64"} or identity.channel != "stable":
        raise ProviderError("Talos Linux automatic updates support stable metal ISOs only.")
    hosts = {
        "api.github.com",
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    }
    client = SafeHttpClient(frozenset(hosts))
    payload = json.loads(
        _text(client, "https://api.github.com/repos/siderolabs/talos/releases/latest")
    )
    version = str(payload.get("tag_name", "")).removeprefix("v")
    filename = f"metal-{identity.architecture}.iso"
    assets = {
        str(asset.get("name")): asset
        for asset in payload.get("assets", [])
        if isinstance(asset, dict)
    }
    asset = assets.get(filename)
    if not version or asset is None:
        raise ProviderError("The latest Talos Linux release lacks the selected metal ISO.")
    digest = str(asset.get("digest", ""))
    if not re.fullmatch(r"sha256:[A-Fa-f0-9]{64}", digest):
        raise ProviderError("The Talos Linux ISO lacks an official SHA-256 digest.")
    size = asset.get("size")
    if not isinstance(size, int) or size <= 0:
        raise ProviderError("The Talos Linux ISO lacks an official download size.")
    return _artifact(
        identity,
        version,
        filename,
        str(asset.get("browser_download_url", "")),
        "sha256",
        digest.removeprefix("sha256:").lower(),
        hosts,
        size_bytes=size,
    )


def _antix(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "antix" or identity.edition not in {
        "full",
        "base",
        "core",
        "net",
    }:
        raise ProviderError("This antiX medium is not supported.")
    if identity.architecture not in {"x86_64", "386"} or identity.channel != "stable":
        raise ProviderError("antiX automatic updates support stable x64 and 386 ISOs only.")
    hosts = {
        "sourceforge.net",
        "downloads.sourceforge.net",
        "netix.dl.sourceforge.net",
    }
    client = SafeHttpClient(frozenset(hosts))
    root = "https://sourceforge.net/projects/antix-linux/files/Final/"
    root_page = _text(client, root)
    versions = re.findall(
        r"/projects/antix-linux/files/Final/antiX-(?P<version>\d+(?:\.\d+)*)/",
        root_page,
        re.IGNORECASE,
    )
    if not versions:
        raise ProviderError("The official antiX release index contains no stable release.")
    version = max(set(versions), key=_version_key)
    release_url = f"{root}antiX-{version}/"
    release_page = _text(client, release_url)
    architecture = "x64" if identity.architecture == "x86_64" else "386"
    if identity.edition == "net":
        filename = f"antiX-{version}-net_{architecture}-net.iso"
    else:
        filename = f"antiX-{version}_{architecture}-{identity.edition}.iso"
    if re.search(rf"\b{re.escape(filename)}\b", release_page, re.IGNORECASE) is None:
        raise ProviderError("The latest antiX release no longer provides this exact ISO variant.")
    download_url = f"{release_url}{filename}/download?use_mirror=netix"
    checksum_url = f"{release_url}{filename}.sha256/download?use_mirror=netix"
    checksum = _checksum(_text(client, checksum_url), filename, "sha256")
    return _artifact(
        identity,
        version,
        filename,
        download_url,
        "sha256",
        checksum,
        hosts,
    )


def _mx_linux(identity: IsoIdentity) -> ReleaseArtifact:
    valid_variants = {
        ("xfce", "standard"),
        ("xfce", "ahs"),
        ("kde", "ahs"),
        ("fluxbox", "standard"),
    }
    if (
        identity.product_id != "mx-linux"
        or (identity.edition, identity.flavor) not in valid_variants
    ):
        raise ProviderError("This MX Linux desktop or AHS variant is not supported.")
    if identity.architecture != "x86_64" or identity.channel != "stable":
        raise ProviderError("MX Linux automatic updates support stable x64 ISOs only.")
    hosts = {
        "sourceforge.net",
        "downloads.sourceforge.net",
        "netix.dl.sourceforge.net",
    }
    client = SafeHttpClient(frozenset(hosts))
    root = "https://sourceforge.net/projects/mx-linux/files/Final/"
    root_page = _text(client, root)
    versions = re.findall(r"\bMX-(?P<version>\d+(?:\.\d+)*)_", root_page, re.IGNORECASE)
    if not versions:
        raise ProviderError("The official MX Linux index contains no stable release.")
    version = max(set(versions), key=_version_key)
    assert identity.edition is not None
    directory = {"xfce": "Xfce", "kde": "KDE", "fluxbox": "Fluxbox"}[identity.edition]
    release_url = f"{root}{directory}/"
    release_page = _text(client, release_url)
    edition = {"xfce": "Xfce", "kde": "KDE", "fluxbox": "fluxbox"}[identity.edition]
    ahs = "_ahs" if identity.edition == "xfce" and identity.flavor == "ahs" else ""
    filename = f"MX-{version}_{edition}{ahs}_x64.iso"
    if re.search(rf"\b{re.escape(filename)}\b", release_page, re.IGNORECASE) is None:
        raise ProviderError("The current MX Linux release lacks this exact desktop variant.")
    download_url = f"{release_url}{filename}/download?use_mirror=netix"
    checksum_url = f"{release_url}{filename}.sha256/download?use_mirror=netix"
    checksum = _checksum(_text(client, checksum_url), filename, "sha256")
    return _artifact(
        identity,
        version,
        filename,
        download_url,
        "sha256",
        checksum,
        hosts,
    )


def _caine(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "caine" or identity.edition != "forensics-live":
        raise ProviderError("This CAINE medium is not supported.")
    if identity.architecture != "x86_64" or identity.channel != "stable":
        raise ProviderError("CAINE automatic updates support stable x86_64 ISOs only.")
    host = "www.caine-live.net"
    client = SafeHttpClient(frozenset({host}))
    page = _text(client, f"https://{host}/page5/page5.html")
    versions = re.findall(r"\bcaine(?P<version>\d+(?:\.\d+)*)\.iso\b", page, re.IGNORECASE)
    if not versions:
        raise ProviderError("The official CAINE page contains no release ISO.")
    version = max(set(versions), key=_version_key)
    filename = f"caine{version}.iso"
    base = f"https://{host}/Downloads/"
    checksum_url = f"https://{host}/page5/{filename}.sha256.txt"
    checksum = _checksum(_text(client, checksum_url), filename, "sha256")
    return _artifact(
        identity,
        version,
        filename,
        base + filename,
        "sha256",
        checksum,
        {host},
    )


def _kaisen_linux(identity: IsoIdentity) -> ReleaseArtifact:
    editions = {"kde", "lxqt", "mate", "xfce", "system-rescue", "netinst"}
    if identity.product_id != "kaisen-linux" or identity.edition not in editions:
        raise ProviderError("This Kaisen Linux medium is not supported.")
    if identity.architecture != "amd64" or identity.channel != "rolling":
        raise ProviderError("Kaisen Linux automatic updates support rolling amd64 ISOs only.")
    hosts = {"kaisenlinux.org", "iso.kaisenlinux.org"}
    client = SafeHttpClient(frozenset(hosts))
    checksums = _text(client, "https://kaisenlinux.org/checksums.txt")
    suffix = {
        "kde": "KDE",
        "lxqt": "LXQT",
        "mate": "MATE",
        "xfce": "XFCE",
        "system-rescue": "SR",
        "netinst": "NETINST",
    }[identity.edition]
    expression = re.compile(
        rf"\b(kaisenlinuxrolling(?P<version>\d+(?:\.\d+)*)-amd64-"
        rf"{suffix}\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(checksums))
    if not matches:
        raise ProviderError("The official Kaisen checksum list lacks this ISO variant.")
    match = max(matches, key=lambda item: _version_key(item.group("version")))
    filename = match.group(1)
    version = match.group("version")
    checksum = _checksum(checksums, filename, "sha256")
    return _artifact(
        identity,
        version,
        filename,
        f"https://iso.kaisenlinux.org/rolling/{filename}",
        "sha256",
        checksum,
        hosts,
    )


def _casuarina_linux(identity: IsoIdentity) -> ReleaseArtifact:
    if identity.product_id != "casuarina-linux" or identity.edition != "base":
        raise ProviderError("This Casuarina Linux medium is not supported.")
    if identity.architecture != "x86_64" or identity.channel != "preview":
        raise ProviderError("Casuarina automatic updates support preview x86_64 ISOs only.")
    hosts = {"casuarina.org", "repo.casuarina.org"}
    client = SafeHttpClient(frozenset(hosts))
    page = _text(client, "https://casuarina.org/download/")
    expression = re.compile(
        r"\b(casuarina-linux-x86_64-LIVE-(?P<version>\d{8})-base\.iso)\b",
        re.IGNORECASE,
    )
    matches = list(expression.finditer(page))
    if not matches:
        raise ProviderError("The official Casuarina page contains no preview ISO.")
    match = max(matches, key=lambda item: item.group("version"))
    filename = match.group(1)
    version = match.group("version")
    base = f"https://repo.casuarina.org/live/{version}/"
    checksum = _checksum(_text(client, base + "sha256sums.txt"), filename, "sha256")
    return _artifact(
        identity,
        version,
        filename,
        base + filename,
        "sha256",
        checksum,
        hosts,
    )
