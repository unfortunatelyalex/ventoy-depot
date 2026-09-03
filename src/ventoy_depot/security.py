from __future__ import annotations

import ipaddress
import json
import re
import socket
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit


class SecurityError(RuntimeError):
    pass


_PROVIDER_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_FINGERPRINT = re.compile(r"^(?:[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64})$")
_HOST = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def validate_https_url(url: str, allowed_hosts: frozenset[str], resolve_dns: bool = True) -> None:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        raise SecurityError("Only credential-free HTTPS URLs are allowed.")
    if hostname not in {host.lower() for host in allowed_hosts}:
        raise SecurityError(f"Host is not allow-listed: {hostname}")
    if ".." in unquote(parsed.path).split("/"):
        raise SecurityError("URL path traversal is not allowed.")
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


def safe_subdirectory(root: Path, *parts: str) -> Path:
    """Create a contained directory without following removable-media symlinks."""
    resolved_root = root.resolve(strict=True)
    current = resolved_root
    for part in parts:
        if not part or part in {".", ".."} or "/" in part or "\\" in part:
            raise SecurityError("Metadata directory contains an unsafe path component.")
        candidate = current / part
        if candidate.is_symlink():
            raise SecurityError("Symlinked metadata directories are not allowed.")
        try:
            candidate.mkdir()
        except FileExistsError:
            pass
        if candidate.is_symlink() or not candidate.is_dir():
            raise SecurityError("Symlinked metadata directories are not allowed.")
        try:
            current = candidate.resolve(strict=True)
            current.relative_to(resolved_root)
        except ValueError as error:
            raise SecurityError("Metadata directory escapes the Ventoy mountpoint.") from error
    return current


def validate_signer_fingerprints(fingerprints: tuple[str, ...] | list[str]) -> None:
    if not fingerprints or any(not _FINGERPRINT.fullmatch(str(item)) for item in fingerprints):
        raise SecurityError("OpenPGP fingerprints must be complete (40 or 64 hex characters).")


def load_and_validate_manifest(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 1024 * 1024:
        raise SecurityError("Manifest exceeds the 1 MiB metadata limit.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SecurityError("Manifest is not valid UTF-8 JSON.") from error
    if not isinstance(payload, dict):
        raise SecurityError("Manifest root must be an object.")
    required = {
        "schema_version",
        "provider_id",
        "display_name",
        "homepage_url",
        "driver",
        "allowed_hosts",
        "capabilities",
        "release_sources",
        "detection",
    }
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
    _validate_registry_shape(payload)
    hosts = _string_list(payload["allowed_hosts"], "host allow-list", allow_empty=False)
    canonical_hosts = [host.rstrip(".").lower() for host in hosts]
    if len(canonical_hosts) != len(set(canonical_hosts)):
        raise SecurityError("Manifest host allow-list contains duplicate hostnames.")
    host_set = frozenset(canonical_hosts)
    if any(not host or not _HOST.fullmatch(host) for host in host_set):
        raise SecurityError("Manifest host allow-list contains an invalid hostname.")
    for path_parts, value in _manifest_values(payload):
        key = path_parts[-1]
        if _is_url_field(key) and value is not None:
            validate_https_url(str(value), host_set, resolve_dns=False)
        if key == "signer_fingerprints":
            if not isinstance(value, list):
                raise SecurityError("OpenPGP fingerprints must be a list.")
            validate_signer_fingerprints([str(item) for item in value])
        if key == "checksum_algorithm" or (key == "algorithm" and "checksum" in path_parts):
            if str(value).lower() not in {"sha256", "sha512"}:
                raise SecurityError("Manifest checksums must use SHA-256 or SHA-512.")
        if key in {"regex", "artifact_regex", "link_regex", "entry_regex"}:
            expression = str(value)
            if not expression or len(expression) > 512 or _looks_catastrophic(expression):
                raise SecurityError("Manifest regex is too large or potentially unsafe.")
            try:
                re.compile(expression)
            except re.error as error:
                raise SecurityError("Manifest regex is invalid.") from error
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
    repeated_broad_atom = (
        r"\((?:\?:|\?P<[^>]+>)?"
        r"(?:\.\*|\.\+|\\[wdsDWS][+*]|\[[^]]+\][+*])"
        r"\)[+*{]"
    )
    return bool(re.search(repeated_broad_atom, expression))


def _is_url_field(key: str) -> bool:
    return (
        key.endswith("_url")
        or key.endswith("_url_template")
        or key
        in {
            "url",
            "url_template",
            "download_url",
        }
    )


def _manifest_values(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    entries: list[tuple[tuple[str, ...], Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            current = (*path, str(key))
            entries.append((current, item))
            entries.extend(_manifest_values(item, current))
    elif isinstance(value, list):
        for item in value:
            entries.extend(_manifest_values(item, path))
    return entries


def _validate_registry_shape(payload: dict[str, Any]) -> None:
    top_level = {
        "schema_version",
        "provider_id",
        "display_name",
        "homepage_url",
        "driver",
        "allowed_hosts",
        "capabilities",
        "release_sources",
        "detection",
        "notes",
    }
    if unknown := set(payload) - top_level:
        raise SecurityError(f"Manifest contains unsupported fields: {', '.join(sorted(unknown))}")
    if not isinstance(payload["display_name"], str) or not 2 <= len(payload["display_name"]) <= 80:
        raise SecurityError("Manifest display name must contain 2-80 characters.")

    capabilities = _object(payload["capabilities"], "capabilities")
    dimensions = {"products", "editions", "flavors", "architectures", "languages", "channels"}
    if set(capabilities) != dimensions:
        raise SecurityError("Manifest capabilities have missing or unsupported dimensions.")
    for dimension in dimensions:
        values = _string_list(capabilities[dimension], f"capability {dimension}", allow_empty=True)
        if dimension in {"products", "architectures", "channels"} and not values:
            raise SecurityError(f"Manifest capability {dimension} must not be empty.")

    sources = payload["release_sources"]
    if not isinstance(sources, list) or not 1 <= len(sources) <= 40:
        raise SecurityError("Manifest must contain 1-40 release sources.")
    for value in sources:
        source = _object(value, "release source")
        required = {
            "source_id",
            "metadata_url",
            "artifact_regex",
            "identity",
            "download",
            "verification",
        }
        if required - source.keys():
            raise SecurityError("Manifest release source is incomplete.")
        if set(source) - (required | {"automatic_download"}):
            raise SecurityError("Manifest release source contains unsupported fields.")
        if not isinstance(source["source_id"], str) or not _SOURCE_ID.fullmatch(
            source["source_id"]
        ):
            raise SecurityError("Manifest release source id is invalid.")
        if not isinstance(source["artifact_regex"], str):
            raise SecurityError("Manifest artifact regex must be a string.")
        if "automatic_download" in source and not isinstance(source["automatic_download"], bool):
            raise SecurityError("Manifest automatic_download flag must be boolean.")
        _validate_identity(source["identity"], capabilities, source["artifact_regex"])
        download = _object(source["download"], "download policy")
        if set(download) - {"strategy", "url_template", "link_regex"}:
            raise SecurityError("Manifest download policy contains unsupported fields.")
        if download.get("strategy") not in {
            "url-template",
            "page-link",
            "release-asset",
            "latest-redirect",
            "user-supplied",
        }:
            raise SecurityError("Manifest download strategy is unsupported.")
        if "link_regex" in download and not isinstance(download["link_regex"], str):
            raise SecurityError("Manifest download link regex must be a string.")
        verification = _object(source["verification"], "verification policy")
        if set(verification) - {"level", "checksum", "signature"}:
            raise SecurityError("Manifest verification policy contains unsupported fields.")
        if verification.get("level") not in {"CHECKSUM", "SIGNED"}:
            raise SecurityError("Manifest verification level must be CHECKSUM or SIGNED.")
        checksum = _object(verification.get("checksum"), "checksum policy")
        if set(checksum) - {"algorithm", "strategy", "url_template", "suffix", "entry_regex"}:
            raise SecurityError("Manifest checksum policy contains unsupported fields.")
        if checksum.get("algorithm") not in {"sha256", "sha512"}:
            raise SecurityError("Manifest checksums must use SHA-256 or SHA-512.")
        if checksum.get("strategy") not in {
            "checksum-list",
            "sidecar",
            "release-asset",
            "release-digest",
            "embedded-json",
            "html-table",
        }:
            raise SecurityError("Manifest checksum strategy is unsupported.")
        for field in ("suffix", "entry_regex"):
            if field in checksum and not isinstance(checksum[field], str):
                raise SecurityError(f"Manifest checksum {field} must be a string.")
        if "signature" in verification:
            signature = _object(verification["signature"], "signature policy")
            if set(signature) - {"strategy", "url_template", "suffix", "signer_fingerprints"}:
                raise SecurityError("Manifest signature policy contains unsupported fields.")
            if signature.get("strategy") not in {"sidecar", "signed-checksum-list"}:
                raise SecurityError("Manifest signature strategy is unsupported.")
            if "suffix" in signature and not isinstance(signature["suffix"], str):
                raise SecurityError("Manifest signature suffix must be a string.")
            fingerprints = _string_list(
                signature.get("signer_fingerprints"),
                "signature fingerprints",
                allow_empty=False,
            )
            validate_signer_fingerprints(fingerprints)
        elif verification["level"] == "SIGNED":
            raise SecurityError("SIGNED release source requires a signature policy.")

    detection = payload["detection"]
    if not isinstance(detection, list) or not 1 <= len(detection) <= 50:
        raise SecurityError("Detection must contain 1-50 rules.")
    for value in detection:
        rule = _object(value, "detection rule")
        if set(rule) != {"regex", "identity", "downloadable"}:
            raise SecurityError("Manifest detection rule is incomplete or has unsupported fields.")
        if not isinstance(rule["downloadable"], bool):
            raise SecurityError("Manifest detection downloadable flag must be boolean.")
        _validate_identity(rule["identity"], capabilities, rule["regex"])

    if "notes" in payload:
        notes = _string_list(payload["notes"], "notes", allow_empty=True)
        if any(len(note) > 500 for note in notes):
            raise SecurityError("Manifest notes must not exceed 500 characters.")


def _validate_identity(value: Any, capabilities: dict[str, Any], expression: str) -> None:
    identity = _object(value, "identity")
    fields = {
        "product_id",
        "edition",
        "flavor",
        "channel",
        "architecture",
        "language",
        "version",
        "build",
    }
    if set(identity) - fields or not {"product_id", "channel", "architecture"} <= set(identity):
        raise SecurityError("Manifest identity is incomplete or contains unsupported fields.")
    for required in ("product_id", "channel", "architecture"):
        if not isinstance(identity[required], str) or not identity[required]:
            raise SecurityError(f"Manifest identity {required} must be a non-empty string.")
    for optional in ("edition", "flavor", "language", "version", "build"):
        if (
            optional in identity
            and identity[optional] is not None
            and not isinstance(identity[optional], str)
        ):
            raise SecurityError(f"Manifest identity {optional} must be a string or null.")
    dimensions = {
        "product_id": "products",
        "edition": "editions",
        "flavor": "flavors",
        "architecture": "architectures",
        "language": "languages",
        "channel": "channels",
    }
    for field, capability in dimensions.items():
        item = identity.get(field)
        if isinstance(item, str) and item.startswith("$group:"):
            group_name = item.removeprefix("$group:")
            try:
                groups = re.compile(expression).groupindex
            except re.error:
                groups = {}
            if not group_name or group_name not in groups:
                raise SecurityError(f"Manifest identity {field} references an unknown regex group.")
        elif item is not None and item not in capabilities[capability]:
            raise SecurityError(f"Manifest identity {field} is not declared in capabilities.")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise SecurityError(f"Manifest {label} must be an object.")
    return value


def _string_list(value: Any, label: str, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise SecurityError(f"Manifest {label} must be a list.")
    if any(not isinstance(item, str) or not item for item in value) or len(value) != len(
        set(value)
    ):
        raise SecurityError(f"Manifest {label} must contain unique non-empty strings.")
    return value
