from __future__ import annotations

import ipaddress
import json
import re
import socket
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit


class SecurityError(RuntimeError):
    pass


_PROVIDER_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_FINGERPRINT = re.compile(r"^[A-Fa-f0-9]{40,64}$")


def validate_https_url(url: str, allowed_hosts: frozenset[str], resolve_dns: bool = True) -> None:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        raise SecurityError("Only credential-free HTTPS URLs are allowed.")
    if hostname not in {host.lower() for host in allowed_hosts}:
        raise SecurityError(f"Host is not allow-listed: {hostname}")
    try:
        addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = {
            ipaddress.ip_address(hostname)
        }
    except ValueError:
        if not resolve_dns:
            return
        try:
            addresses = {
                ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(hostname, 443)
            }
        except OSError as error:
            raise SecurityError(f"Could not resolve metadata host: {hostname}") from error
    if any(not address.is_global for address in addresses):
        raise SecurityError("Private, loopback, reserved and link-local destinations are blocked.")


def safe_filename(filename: str) -> str:
    pure = PurePosixPath(filename)
    if pure.is_absolute() or len(pure.parts) != 1 or filename in {"", ".", ".."}:
        raise SecurityError("Provider filename must not contain a path.")
    if "\\" in filename or "\x00" in filename:
        raise SecurityError("Provider filename contains unsafe characters.")
    return filename


def load_and_validate_manifest(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 1024 * 1024:
        raise SecurityError("Manifest exceeds the 1 MiB metadata limit.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SecurityError("Manifest is not valid UTF-8 JSON.") from error
    if not isinstance(payload, dict):
        raise SecurityError("Manifest root must be an object.")
    required = {"schema_version", "provider_id", "driver", "allowed_hosts", "detection"}
    missing = required - payload.keys()
    if missing:
        raise SecurityError(f"Manifest is missing fields: {', '.join(sorted(missing))}")
    if payload["schema_version"] != 1 or not _PROVIDER_ID.fullmatch(str(payload["provider_id"])):
        raise SecurityError("Unsupported schema version or invalid provider id.")
    allowed_drivers = {
        "github-releases",
        "gitlab-releases",
        "static-json",
        "directory-index",
        "checksum-list",
        "sidecar",
        "static-html",
        "latest-redirect",
    }
    if payload["driver"] not in allowed_drivers:
        raise SecurityError("Manifest driver is not supported.")
    hosts = payload["allowed_hosts"]
    if not isinstance(hosts, list) or not hosts:
        raise SecurityError("Manifest needs a non-empty host allow-list.")
    host_set = frozenset(str(host).rstrip(".").lower() for host in hosts)
    for key, value in payload.items():
        if key.endswith("_url") and value is not None:
            validate_https_url(str(value), host_set, resolve_dns=False)
    for fingerprint in payload.get("signer_fingerprints", []):
        if not _FINGERPRINT.fullmatch(str(fingerprint)):
            raise SecurityError("OpenPGP fingerprints must be complete (40-64 hex characters).")
    checksum = str(payload.get("checksum_algorithm", "sha256")).lower()
    if checksum not in {"sha256", "sha512"}:
        raise SecurityError("Manifest checksums must use SHA-256 or SHA-512.")
    detection = payload["detection"]
    if not isinstance(detection, list) or len(detection) > 50:
        raise SecurityError("Detection must be a list with at most 50 rules.")
    for rule in detection:
        expression = str(rule.get("regex", "")) if isinstance(rule, dict) else ""
        if len(expression) > 512 or _looks_catastrophic(expression):
            raise SecurityError("Detection regex is too large or potentially unsafe.")
        try:
            re.compile(expression)
        except re.error as error:
            raise SecurityError("Detection regex is invalid.") from error
    return payload


def _looks_catastrophic(expression: str) -> bool:
    return bool(re.search(r"\([^)]*[+*][^)]*\)[+*{]", expression))
