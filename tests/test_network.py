import urllib.error
import urllib.request

import pytest

from ventoy_depot import network
from ventoy_depot.network import SafeHttpClient


class FakeResponse:
    def __init__(self, length: object, data: bytes = b"") -> None:
        self.headers = {"Content-Length": length}
        self.data = data
        self.closed = False

    def read(self, amount: int = -1) -> bytes:
        return self.data[:amount]

    def close(self) -> None:
        self.closed = True


def test_metadata_closes_response_when_content_length_is_invalid(monkeypatch) -> None:
    response = FakeResponse("invalid")
    monkeypatch.setattr(SafeHttpClient, "open", lambda self, url: response)

    with pytest.raises(urllib.error.URLError, match="invalid Content-Length"):
        SafeHttpClient(frozenset({"example.test"})).metadata("https://example.test/data")

    assert response.closed


def test_metadata_closes_response_when_read_fails(monkeypatch) -> None:
    response = FakeResponse("1")

    def fail_read(amount: int = -1) -> bytes:
        raise OSError("connection lost")

    response.read = fail_read  # type: ignore[method-assign]
    monkeypatch.setattr(SafeHttpClient, "open", lambda self, url: response)

    with pytest.raises(OSError, match="connection lost"):
        SafeHttpClient(frozenset({"example.test"})).metadata("https://example.test/data")

    assert response.closed


def test_configured_proxy_is_used_only_for_https_requests(monkeypatch) -> None:
    captured: list[urllib.request.BaseHandler] = []
    response = FakeResponse("0")

    class Opener:
        def open(self, _request, timeout):
            assert timeout == 30.0
            return response

    def build_opener(*handlers):
        captured.extend(handlers)
        return Opener()

    monkeypatch.setattr(network.urllib.request, "build_opener", build_opener)
    monkeypatch.setattr(network, "validate_https_url", lambda *_args: None)
    monkeypatch.setattr(network, "_PROXY", "http://proxy.example:8080")

    SafeHttpClient(frozenset({"example.test"})).open("https://example.test/data")

    proxy = next(item for item in captured if isinstance(item, urllib.request.ProxyHandler))
    assert proxy.proxies == {"https": "http://proxy.example:8080"}
