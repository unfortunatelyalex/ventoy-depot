from __future__ import annotations

import json

import pytest

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


@pytest.mark.parametrize(
    ("edition", "flavor", "directory", "filename", "checksum_name"),
    [
        (
            "xfce",
            "live",
            "Spins",
            "Fedora-Xfce-Live-44-1.7.x86_64.iso",
            "Fedora-Spins-44-1.7-x86_64-CHECKSUM",
        ),
        (
            "silverblue",
            "ostree",
            "Silverblue",
            "Fedora-Silverblue-ostree-x86_64-44-1.7.iso",
            "Fedora-Silverblue-44-1.7-x86_64-CHECKSUM",
        ),
    ],
)
def test_fedora_resolver_supports_official_spins_and_silverblue(
    monkeypatch,
    edition: str,
    flavor: str,
    directory: str,
    filename: str,
    checksum_name: str,
) -> None:
    digest = "c" * 64
    root = "https://dl.fedoraproject.org/pub/fedora/linux/releases/"
    base = f"{root}44/{directory}/x86_64/iso/"

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            if url == root:
                return b'<a href="43/">43</a><a href="44/">44</a>'
            if url == base:
                return (
                    f'<a href="{filename}">{filename}</a>'
                    f'<a href="{checksum_name}">{checksum_name}</a>'
                ).encode()
            assert url == base + checksum_name
            return f"SHA256 ({filename}) = {digest}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "fedora", "fedora", edition, flavor, "stable", "x86_64", None, "43", "1.1"
    )

    artifact = resolvers.resolve_release("fedora", installed)

    assert artifact.filename == filename
    assert artifact.checksum == digest
    assert artifact.identity is not None
    assert artifact.identity.variant_key() == installed.variant_key()


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


def test_netboot_xyz_resolver_uses_github_asset_digest(monkeypatch) -> None:
    digest = "5" * 64
    payload = {
        "tag_name": "3.0.2",
        "assets": [
            {
                "name": "netboot.xyz-arm64.iso",
                "browser_download_url": (
                    "https://github.com/netbootxyz/netboot.xyz/releases/download/3.0.2/"
                    "netboot.xyz-arm64.iso"
                ),
                "digest": f"sha256:{digest}",
                "size": 42,
            }
        ],
    }

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://api.github.com/repos/netbootxyz/netboot.xyz/releases/latest"
            return json.dumps(payload).encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "netboot-xyz", "netboot-xyz", "standard", None, "stable", "arm64", None, None, None
    )
    artifact = resolvers.resolve_release("netboot-xyz", installed)

    assert artifact.version == "3.0.2"
    assert artifact.filename == "netboot.xyz-arm64.iso"
    assert artifact.size_bytes == 42
    assert artifact.checksum == digest


def test_gentoo_resolver_uses_latest_autobuild_sha256(monkeypatch) -> None:
    filename = "install-amd64-minimal-20260830T151604Z.iso"
    digest = "6" * 64
    base = "https://distfiles.gentoo.org/releases/amd64/autobuilds/current-install-amd64-minimal/"

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            if url == base:
                return b"install-amd64-minimal-20260823T151604Z.iso\n" + filename.encode()
            assert url == base + filename + ".sha256"
            return (
                "-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA512\n\n"
                f"# SHA256 HASH\n{digest}  {filename}\n"
            ).encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "gentoo", "gentoo", "minimal", None, "stable", "amd64", None, "20260823T151604Z", None
    )
    artifact = resolvers.resolve_release("gentoo", installed)

    assert artifact.version == "20260830T151604Z"
    assert artifact.filename == filename
    assert artifact.download_url == base + filename
    assert artifact.checksum == digest


def test_hirens_resolver_uses_official_page_metadata(monkeypatch) -> None:
    digest = "7" * 64
    page = f"""
        <h2>Hiren&#8217;s BootCD PE x64 (v1.0.8)</h2>
        <a href=\"https://www.hirensbootcd.org/files/HBCD_PE_x64.iso\">ISO</a>
        <p>File size (3291686912 bytes)</p>
        <p>ISO SHA-256</p><code>{digest}</code>
    """

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://www.hirensbootcd.org/download/"
            return page.encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "hirens-bootcd-pe",
        "hirens-bootcd-pe",
        "pe",
        None,
        "stable",
        "x86_64",
        None,
        None,
        None,
    )
    artifact = resolvers.resolve_release("hirens-bootcd-pe", installed)

    assert artifact.version == "1.0.8"
    assert artifact.filename == "HBCD_PE_x64.iso"
    assert artifact.size_bytes == 3291686912
    assert artifact.checksum == digest


def test_shredos_resolver_preserves_architecture_and_image_variant(monkeypatch) -> None:
    filename = "shredos-2025.11_31_i686_v0.42_20260716_lite_plus-partition.iso"
    digest = "8" * 64
    payload = {
        "assets": [
            {
                "name": filename,
                "browser_download_url": (
                    "https://github.com/PartialVolume/shredos.x86_64/releases/download/"
                    f"v2025.11_31_x86-64_0.42/{filename}"
                ),
                "digest": f"sha256:{digest}",
                "size": 123,
            }
        ]
    }

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == (
                "https://api.github.com/repos/PartialVolume/shredos.x86_64/releases/latest"
            )
            return json.dumps(payload).encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "shredos",
        "shredos",
        "lite",
        "plus-partition",
        "stable",
        "i686",
        None,
        "2025.11_30",
        "0.41_20260601",
    )
    artifact = resolvers.resolve_release("shredos", installed)

    assert artifact.filename == filename
    assert artifact.version == "2025.11_31"
    assert artifact.build == "0.42_20260716"
    assert artifact.checksum == digest
    assert artifact.identity is not None
    assert artifact.identity.variant_key() == installed.variant_key()


def test_netbsd_resolver_uses_latest_release_sha512(monkeypatch) -> None:
    filename = "NetBSD-11.0-amd64.iso"
    digest = "9" * 128
    root = "https://cdn.netbsd.org/pub/NetBSD/"

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            if url == root:
                return b'<a href="NetBSD-10.1/">old</a><a href="NetBSD-11.0/">new</a>'
            assert url == root + "NetBSD-11.0/images/SHA512"
            return f"SHA512 ({filename}) = {digest}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "netbsd", "netbsd", "installer", None, "release", "amd64", None, "10.1", None
    )
    artifact = resolvers.resolve_release("netbsd", installed)

    assert artifact.version == "11.0"
    assert artifact.filename == filename
    assert artifact.download_url == root + f"NetBSD-11.0/images/{filename}"
    assert artifact.checksum_algorithm == "sha512"
    assert artifact.checksum == digest


def test_porteux_resolver_preserves_desktop_and_uses_release_digest(monkeypatch) -> None:
    filename = "porteux-2.8-current-xfce-4.20-x86_64.iso"
    digest = "a" * 64
    payload = {
        "assets": [
            {
                "name": filename,
                "browser_download_url": (
                    "https://github.com/porteux/porteux/releases/download/v2.8/" + filename
                ),
                "digest": f"sha256:{digest}",
                "size": 607125504,
            }
        ]
    }

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://api.github.com/repos/porteux/porteux/releases/latest"
            return json.dumps(payload).encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "porteux", "porteux", "xfce", None, "current", "x86_64", None, "2.7", "4.20"
    )
    artifact = resolvers.resolve_release("porteux", installed)

    assert artifact.version == "2.8"
    assert artifact.build == "4.20"
    assert artifact.filename == filename
    assert artifact.size_bytes == 607125504
    assert artifact.checksum == digest
    assert artifact.identity is not None
    assert artifact.identity.variant_key() == installed.variant_key()


def test_ghostbsd_resolver_preserves_community_desktop(monkeypatch) -> None:
    filename = "GhostBSD-26.1-R15.0p2-XFCE.iso"
    digest = "b" * 64
    url = f"https://download.ghostbsd.org/releases/amd64/26.1-R15.0p2/{filename}"
    page = f'<a href="{url}">download</a>'

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, requested: str) -> bytes:
            if requested == "https://www.ghostbsd.org/download":
                return page.encode()
            assert requested == url + ".sha256"
            return f"SHA256 ({filename}) = {digest}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "ghostbsd",
        "ghostbsd",
        "xfce",
        None,
        "community",
        "amd64",
        None,
        "25.02-R14.3p2",
        None,
    )
    artifact = resolvers.resolve_release("ghostbsd", installed)

    assert artifact.version == "26.1-R15.0p2"
    assert artifact.filename == filename
    assert artifact.download_url == url
    assert artifact.checksum == digest
    assert artifact.identity is not None
    assert artifact.identity.variant_key() == installed.variant_key()


def test_ghostbsd_resolver_rejects_cross_channel_switch() -> None:
    identity = IsoIdentity(
        "ghostbsd", "ghostbsd", "xfce", None, "official", "amd64", None, None, None
    )

    with pytest.raises(resolvers.ProviderError, match="do not match"):
        resolvers.resolve_release("ghostbsd", identity)


def test_haiku_resolver_uses_official_page_checksum_and_cdn(monkeypatch) -> None:
    filename = "haiku-r1beta6-x86_64-anyboot.iso"
    digest = "c" * 64
    page = f"{digest}  {filename}\n"

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, url: str) -> bytes:
            assert url == "https://www.haiku-os.org/get-haiku/"
            return page.encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "haiku", "haiku", "anyboot", None, "stable", "x86_64", None, "r1beta5", None
    )
    artifact = resolvers.resolve_release("haiku", installed)

    assert artifact.version == "r1beta6"
    assert artifact.filename == filename
    assert artifact.download_url == ("https://haiku-release.cdn.haiku-os.org/r1beta6/" + filename)
    assert artifact.checksum == digest
    assert artifact.identity is not None
    assert artifact.identity.variant_key() == installed.variant_key()


def test_solus_resolver_preserves_desktop_and_uses_sidecar(monkeypatch) -> None:
    filename = "Solus-Plasma-Release-2026-04-18.iso"
    digest = "d" * 64
    url = f"https://downloads.getsol.us/isos/2026-04-18/{filename}"

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, requested: str) -> bytes:
            if requested == "https://getsol.us/download/":
                return f'<a href="{url}">{filename}</a>'.encode()
            assert requested == url + ".sha256sum"
            return f"{digest}  {filename}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "solus", "solus", "plasma", None, "stable", "x86_64", None, "2025-01-26", None
    )
    artifact = resolvers.resolve_release("solus", installed)

    assert artifact.version == "2026-04-18"
    assert artifact.filename == filename
    assert artifact.download_url == url
    assert artifact.checksum == digest
    assert artifact.identity is not None
    assert artifact.identity.variant_key() == installed.variant_key()


@pytest.mark.parametrize(
    ("channel", "filename", "url"),
    [
        (
            "stable",
            "TrueNAS-SCALE-25.10.7.iso",
            "https://download.sys.truenas.net/TrueNAS-SCALE-Goldeye/25.10.7/"
            "TrueNAS-SCALE-25.10.7.iso",
        ),
        (
            "beta",
            "TrueNAS-26.0.0-BETA.3.iso",
            "https://iso.sys.truenas.net/TrueNAS-26-BETA/26.0.0-BETA.3/TrueNAS-26.0.0-BETA.3.iso",
        ),
    ],
)
def test_truenas_resolver_preserves_release_channel(
    monkeypatch, channel: str, filename: str, url: str
) -> None:
    digest = "e" * 64

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, requested: str) -> bytes:
            if requested == "https://www.truenas.com/download-truenas-community-edition/":
                return f'<a href="{url}">{filename}</a>'.encode()
            assert requested == url + ".sha256"
            return digest.encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity(
        "truenas", "truenas", "community", None, channel, "x86_64", None, None, None
    )
    artifact = resolvers.resolve_release("truenas", installed)

    assert artifact.filename == filename
    assert artifact.download_url == url
    assert artifact.checksum == digest
    assert artifact.identity is not None
    assert artifact.identity.variant_key() == installed.variant_key()


def test_tails_resolver_uses_publisher_bound_iso_metadata(monkeypatch) -> None:
    digest = "f" * 64
    filename = "tails-amd64-7.12.iso"
    url = f"https://download.tails.net/tails/stable/tails-amd64-7.12/{filename}"
    payload = {
        "installations": [
            {
                "version": "7.12",
                "installation-paths": [
                    {
                        "type": "img",
                        "target-files": [{"url": "https://example.invalid/tails.img"}],
                    },
                    {
                        "type": "iso",
                        "target-files": [{"url": url, "sha256": digest, "size": 123}],
                    },
                ],
            }
        ]
    }

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, requested: str) -> bytes:
            assert requested == "https://tails.net/install/v2/Tails/amd64/stable/latest.json"
            return json.dumps(payload).encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity("tails", "tails", "iso", None, "stable", "amd64", None, "7.11", None)
    artifact = resolvers.resolve_release("tails", installed)

    assert artifact.version == "7.12"
    assert artifact.filename == filename
    assert artifact.download_url == url
    assert artifact.size_bytes == 123
    assert artifact.checksum == digest
    assert "mirror.netcologne.de" in artifact.allowed_hosts
    assert artifact.identity is not None
    assert artifact.identity.variant_key() == installed.variant_key()


def test_tails_resolver_rejects_unbound_filename(monkeypatch) -> None:
    payload = {
        "installations": [
            {
                "version": "7.12",
                "installation-paths": [
                    {
                        "type": "iso",
                        "target-files": [
                            {
                                "url": "https://download.tails.net/tails/other.iso",
                                "sha256": "f" * 64,
                                "size": 123,
                            }
                        ],
                    }
                ],
            }
        ]
    }

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, _url: str) -> bytes:
            return json.dumps(payload).encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    identity = IsoIdentity("tails", "tails", "iso", None, "stable", "amd64", None, "7.11", None)

    with pytest.raises(resolvers.ProviderError, match="not bound"):
        resolvers.resolve_release("tails", identity)


def test_grml_resolver_uses_direct_official_master_and_sidecar(monkeypatch) -> None:
    filename = "grml-small-2026.09-arm64.iso"
    digest = "1" * 64
    url = f"https://ftp-master.grml.org/{filename}"

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def metadata(self, requested: str) -> bytes:
            if requested == "https://grml.org/download/":
                return b"grml-small-2026.04-arm64.iso\n" + filename.encode() + b"\n"
            assert requested == url + ".sha256"
            return f"{digest}  {filename}\n".encode()

    monkeypatch.setattr(resolvers, "SafeHttpClient", FakeClient)
    installed = IsoIdentity("grml", "grml", "small", None, "stable", "arm64", None, "2026.04", None)
    artifact = resolvers.resolve_release("grml", installed)

    assert artifact.version == "2026.09"
    assert artifact.filename == filename
    assert artifact.download_url == url
    assert artifact.checksum == digest
    assert artifact.identity is not None
    assert artifact.identity.variant_key() == installed.variant_key()


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
