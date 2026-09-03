from __future__ import annotations

import json

from ventoy_depot.models import IsoIdentity
from ventoy_depot.providers import resolvers


def identity(provider: str, edition: str | None = None) -> IsoIdentity:
    return IsoIdentity(provider, provider, edition, None, "stable", "amd64", None, "22.04", None)


def test_checksum_parser_accepts_plain_and_bsd_formats() -> None:
    digest = "a" * 64
    filename = "example.iso"
    assert resolvers._checksum(f"{digest}  {filename}\n", filename, "sha256") == digest
    assert resolvers._checksum(f"SHA256 ({filename}) = {digest}\n", filename, "sha256") == digest


def test_pop_os_uses_official_variant_api(monkeypatch) -> None:
    payload = {
        "version": "24.04",
        "url": "https://iso.pop-os.org/24.04/amd64/nvidia/27/pop-os_24.04_amd64_nvidia_27.iso",
        "size": 1234,
        "sha_sum": "b" * 64,
        "build": "27",
    }

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://api.pop-os.org/builds/24.04/nvidia?arch=amd64"
            return json.dumps(payload).encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    artifact = resolvers.resolve_release("pop-os", identity("pop-os", "nvidia"))

    assert artifact.filename == "pop-os_24.04_amd64_nvidia_27.iso"
    assert artifact.size_bytes == 1234
    assert artifact.checksum == "b" * 64


def test_gparted_resolver_uses_official_sha256_list(monkeypatch) -> None:
    filename = "gparted-live-1.8.1-6-amd64.iso"
    digest = "c" * 64

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://gparted.org/gparted-live/stable/CHECKSUMS.TXT"
            return f"### SHA256SUMS:\n{digest}  {filename}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    artifact = resolvers.resolve_release("gparted-live", identity("gparted-live", "live"))

    assert artifact.filename == filename
    assert artifact.checksum == digest
    assert artifact.download_url.startswith("https://downloads.sourceforge.net/project/gparted/")


def test_cachyos_resolver_uses_latest_matching_official_directory(monkeypatch) -> None:
    filename = "cachyos-desktop-linux-260809.iso"
    digest = "f" * 64

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            if url == "https://mirror.cachyos.org/ISO/desktop/":
                return b'<a href="260628/">old</a><a href="260809/">new</a>'
            assert url == f"https://mirror.cachyos.org/ISO/desktop/260809/{filename}.sha256"
            return f"{digest}  {filename}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "cachyos", "cachyos", "desktop", None, "stable", "x86_64", None, "260628", None
    )
    artifact = resolvers.resolve_release("cachyos", installed)

    assert artifact.filename == filename
    assert artifact.identity is not None
    assert artifact.identity.edition == "desktop"
    assert artifact.identity.version == "260809"


def test_clonezilla_resolver_preserves_debian_or_ubuntu_base(monkeypatch) -> None:
    filename = "clonezilla-live-3.3.3-15-amd64.iso"
    digest = "1" * 64

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://clonezilla.org/downloads/stable/checksums.php"
            return f"### SHA256SUMS:\n{digest}  {filename}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "clonezilla",
        "clonezilla-live",
        "debian",
        None,
        "stable",
        "amd64",
        None,
        "3.3.2-1",
        None,
    )
    artifact = resolvers.resolve_release("clonezilla", installed)

    assert artifact.filename == filename
    assert artifact.checksum == digest
    assert artifact.identity is not None and artifact.identity.edition == "debian"


def test_systemrescue_resolver_uses_official_sidecar(monkeypatch) -> None:
    filename = "systemrescue-13.02-amd64.iso"
    digest = "2" * 64

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            if url == "https://www.system-rescue.org/Download/":
                return f"Download {filename}".encode()
            assert url == f"https://www.system-rescue.org/releases/13.02/{filename}.sha256"
            return f"{digest} *{filename}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "systemrescue", "systemrescue", "live", None, "stable", "amd64", None, "12.00", None
    )
    artifact = resolvers.resolve_release("systemrescue", installed)

    assert artifact.filename == filename
    assert artifact.checksum == digest


def test_proxmox_resolver_preserves_product_and_architecture(monkeypatch) -> None:
    filename = "proxmox-ve_9.2-1-arm64.iso"
    digest = "3" * 64

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://enterprise.proxmox.com/iso/"
            return f"{filename}\nSHA256: {digest}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "proxmox",
        "proxmox-ve",
        "installer",
        None,
        "stable",
        "arm64",
        None,
        "9.1-1",
        None,
    )
    artifact = resolvers.resolve_release("proxmox", installed)

    assert artifact.filename == filename
    assert artifact.checksum == digest
    assert artifact.identity is not None
    assert artifact.identity.product_id == "proxmox-ve"
    assert artifact.identity.architecture == "arm64"


def test_rescuezilla_resolver_preserves_ubuntu_base(monkeypatch) -> None:
    filename = "rescuezilla-2.6.2-64bit.resolute.iso"
    digest = "4" * 64
    payload = {
        "tag_name": "2.6.2",
        "assets": [
            {
                "name": filename,
                "browser_download_url": f"https://github.com/rescuezilla/rescuezilla/releases/download/2.6.2/{filename}",
                "digest": f"sha256:{digest}",
                "size": 123,
            }
        ],
    }

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://api.github.com/repos/rescuezilla/rescuezilla/releases/latest"
            return json.dumps(payload).encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "rescuezilla",
        "rescuezilla",
        "live",
        "resolute",
        "stable",
        "amd64",
        None,
        "2.6.1",
        None,
    )
    artifact = resolvers.resolve_release("rescuezilla", installed)

    assert artifact.filename == filename
    assert artifact.checksum == digest
    assert artifact.size_bytes == 123


def test_kali_resolver_preserves_image_type_and_architecture(monkeypatch) -> None:
    filename = "kali-linux-2026.2-live-amd64.iso"
    digest = "d" * 64

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://archive.kali.org/kali-images/current/SHA256SUMS"
            return f"{digest}  {filename}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    artifact = resolvers.resolve_release("kali-linux", identity("kali-linux", "live"))

    assert artifact.filename == filename
    assert artifact.version == "2026.2"
    assert artifact.checksum == digest


def test_nixos_resolver_maps_legacy_plasma_to_current_graphical_iso(monkeypatch) -> None:
    filename = "nixos-graphical-26.05.8846.a3116115851d-x86_64-linux.iso"
    digest = "e" * 64

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            if url == "https://nixos.org/download/":
                return b"https://channels.nixos.org/nixos-26.05/latest-nixos-graphical"
            assert url.endswith("latest-nixos-graphical-x86_64-linux.iso.sha256")
            return f"{digest}  {filename}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "nixos",
        "nixos",
        "graphical",
        "plasma5",
        "stable",
        "x86_64",
        None,
        "23.11.7202.e7cc61784ddf",
        None,
    )
    artifact = resolvers.resolve_release("nixos", installed)

    assert artifact.filename == filename
    assert artifact.version == "26.05.8846.a3116115851d"
    assert artifact.checksum == digest


def test_alpine_resolver_preserves_edition_and_architecture(monkeypatch) -> None:
    filename = "alpine-extended-3.24.1-x86_64.iso"
    url = f"https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/x86_64/{filename}"
    digest = "6" * 64

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, requested: str) -> bytes:
            if requested == "https://www.alpinelinux.org/downloads/":
                return f'<a href="{url}">{filename}</a>'.encode()
            assert requested == url + ".sha256"
            return f"{digest}  {filename}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "alpine", "alpine-linux", "extended", None, "stable", "x86_64", None, "3.23.4", None
    )
    artifact = resolvers.resolve_release("alpine", installed)

    assert artifact.filename == filename
    assert artifact.checksum == digest
    assert artifact.identity is not None
    assert artifact.identity.variant_key() == installed.variant_key()


def test_opensuse_resolver_uses_latest_matching_snapshot(monkeypatch) -> None:
    filename = "openSUSE-Tumbleweed-KDE-Live-aarch64-Snapshot20260830-Media.iso"
    base = "https://download.opensuse.org/download/ports/aarch64/tumbleweed/iso/"
    digest = "7" * 64

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, requested: str) -> bytes:
            if requested == base:
                return (
                    f"openSUSE-Tumbleweed-KDE-Live-aarch64-Snapshot20260801-Media.iso\n{filename}\n"
                ).encode()
            assert requested == base + filename + ".sha256"
            return f"{digest}  {filename}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "opensuse-tumbleweed",
        "opensuse-tumbleweed",
        "kde-live",
        None,
        "rolling",
        "aarch64",
        None,
        "20260801",
        None,
    )
    artifact = resolvers.resolve_release("opensuse-tumbleweed", installed)

    assert artifact.filename == filename
    assert artifact.version == "20260830"
    assert artifact.checksum == digest


def test_freebsd_resolver_preserves_medium_and_architecture(monkeypatch) -> None:
    filename = "FreeBSD-15.0-RELEASE-amd64-dvd1.iso"
    root = "https://download.freebsd.org/ftp/releases/ISO-IMAGES/"
    digest = "8" * 64

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, requested: str) -> bytes:
            if requested == root:
                return b'<a href="14.3/">14.3</a><a href="15.0/">15.0</a>'
            assert requested == root + "15.0/CHECKSUM.SHA256-FreeBSD-15.0-RELEASE-amd64"
            return f"SHA256 ({filename}) = {digest}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "freebsd", "freebsd", "dvd1", None, "release", "amd64", None, "14.3", None
    )
    artifact = resolvers.resolve_release("freebsd", installed)

    assert artifact.filename == filename
    assert artifact.checksum == digest
    assert artifact.identity is not None
    assert artifact.identity.variant_key() == installed.variant_key()


def test_rocky_resolver_stays_on_major_channel_and_edition(monkeypatch) -> None:
    filename = "Rocky-9.8-x86_64-minimal.iso"
    base = "https://download.rockylinux.org/pub/rocky/9/isos/x86_64/"
    digest = "9" * 64

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, requested: str) -> bytes:
            assert requested == base + "CHECKSUM"
            return f"SHA256 ({filename}) = {digest}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "rocky-linux", "rocky-linux", "minimal", None, "9", "x86_64", None, "9.6", None
    )
    artifact = resolvers.resolve_release("rocky-linux", installed)

    assert artifact.filename == filename
    assert artifact.checksum == digest
    assert artifact.identity is not None
    assert artifact.identity.channel == "9"
    assert artifact.identity.edition == "minimal"


def test_almalinux_resolver_preserves_architecture_and_major_channel(monkeypatch) -> None:
    filename = "AlmaLinux-10.2-aarch64-boot.iso"
    base = "https://repo.almalinux.org/almalinux/10/isos/aarch64/"
    digest = "a" * 64

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, requested: str) -> bytes:
            assert requested == base + "CHECKSUM"
            return f"SHA256 ({filename}) = {digest}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "almalinux", "almalinux", "boot", None, "10", "aarch64", None, "10.1", None
    )
    artifact = resolvers.resolve_release("almalinux", installed)

    assert artifact.filename == filename
    assert artifact.version == "10.2"
    assert artifact.checksum == digest
    assert artifact.identity is not None
    assert artifact.identity.variant_key() == installed.variant_key()
