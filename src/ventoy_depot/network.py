from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import Message
from typing import IO, Protocol, cast
from urllib.parse import urljoin

from .security import validate_https_url

_PROXY: str | None = None


def configure_proxy(proxy: str | None) -> None:
    global _PROXY
    _PROXY = proxy


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


class HttpResponse(Protocol):
    status: int
    headers: Message

    def read(self, amt: int = -1) -> bytes: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class SafeHttpClient:
    allowed_hosts: frozenset[str]
    timeout: float = 30.0
    max_redirects: int = 5
    max_metadata_bytes: int = 8 * 1024 * 1024
    user_agent: str = "ventoy-depot/0.2"

    def open(self, url: str, headers: dict[str, str] | None = None) -> HttpResponse:
        handlers: list[urllib.request.BaseHandler] = [_NoRedirect()]
        if _PROXY is not None:
            handlers.insert(0, urllib.request.ProxyHandler({"https": _PROXY}))
        opener = urllib.request.build_opener(*handlers)
        current = url
        for _ in range(self.max_redirects + 1):
            validate_https_url(current, self.allowed_hosts)
            request = urllib.request.Request(
                current, headers={"User-Agent": self.user_agent, **(headers or {})}
            )
            try:
                return cast(HttpResponse, opener.open(request, timeout=self.timeout))
            except urllib.error.HTTPError as error:
                if error.code not in {301, 302, 303, 307, 308}:
                    error.close()
                    raise
                location = error.headers.get("Location")
                error.close()
                if not location:
                    raise
                current = urljoin(current, location)
        raise urllib.error.URLError("Too many redirects")

    def metadata(self, url: str) -> bytes:
        response = self.open(url)
        try:
            try:
                length = int(response.headers.get("Content-Length", 0))
            except (TypeError, ValueError) as error:
                raise urllib.error.URLError("Metadata has an invalid Content-Length") from error
            if length > self.max_metadata_bytes:
                raise urllib.error.URLError("Metadata exceeds the configured size limit")
            data = response.read(self.max_metadata_bytes + 1)
        finally:
            response.close()
        if len(data) > self.max_metadata_bytes:
            raise urllib.error.URLError("Metadata exceeds the configured size limit")
        return data
