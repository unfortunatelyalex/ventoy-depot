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
