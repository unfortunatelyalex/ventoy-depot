from __future__ import annotations

import importlib
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from ..models import DetectedIso, IsoIdentity, ReleaseArtifact
from ..network import SafeHttpClient
from ..security import safe_filename
from .base import Provider, ProviderCapabilities, ProviderError

regex: Any = importlib.import_module("regex")


class ManifestProvider(Provider):
    """A validated data-only provider: manifests never execute Python code."""

    def __init__(self, manifest: dict[str, Any], *, origin: str = "registry") -> None:
        self.manifest = manifest
        self.origin = origin
        self.custom = origin == "custom"
        self.provider_id = str(manifest["provider_id"])
        self.display_name = str(manifest["display_name"])
        capabilities = manifest["capabilities"]
        self.capabilities = ProviderCapabilities(
            tuple(str(item).lower() for item in capabilities["editions"]),
            tuple(str(item).lower() for item in capabilities["architectures"]),
            tuple(str(item).lower() for item in capabilities["languages"]),
            tuple(str(item).lower() for item in capabilities["channels"]),
            tuple(str(item).lower() for item in capabilities["flavors"]),
        )
        self._products = tuple(str(item).lower() for item in capabilities["products"])
        self._rules = tuple(
            (regex.compile(str(rule["regex"]), regex.IGNORECASE), rule)
            for rule in manifest["detection"]
        )
        self._blocked_variants: set[
            tuple[str, str, str | None, str | None, str, str, str | None]
        ] = set()

    @property
    def products(self) -> tuple[str, ...]:
        return self._products

    def detect(self, path: Path) -> DetectedIso | None:
        for expression, rule in self._rules:
            try:
                match = expression.fullmatch(path.name, timeout=0.05)
            except TimeoutError:
                continue
            if match is None:
                continue
            values = {
                field: _resolve_value(value, match) for field, value in rule["identity"].items()
            }
            identity = IsoIdentity(
                provider_id=self.provider_id,
                product_id=str(values["product_id"]).lower(),
                edition=_optional(values.get("edition")),
                flavor=_optional(values.get("flavor")),
                channel=str(values["channel"]).lower(),
                architecture=_architecture(str(values["architecture"])),
                language=_optional(values.get("language")),
                version=_optional(values.get("version"), lower=False),
                build=_optional(values.get("build"), lower=False),
            )
            if not rule["downloadable"]:
                self._blocked_variants.add(identity.variant_key())
            return DetectedIso(path, identity, 0.98, "signed-registry-filename")
        return None

    def resolve(self, identity: IsoIdentity) -> ReleaseArtifact:
        if identity.provider_id != self.provider_id or identity.product_id not in self._products:
            raise ProviderError("Provider identity is not supported by this manifest.")
        self._validate("edition", identity.edition, self.capabilities.editions)
        self._validate("flavor", identity.flavor, self.capabilities.flavors)
        self._validate("architecture", identity.architecture, self.capabilities.architectures)
        self._validate("language", identity.language, self.capabilities.languages)
        self._validate("channel", identity.channel, self.capabilities.channels)
        if identity.variant_key() in self._blocked_variants:
            raise ProviderError("This detected ISO is intentionally not downloadable.")
        # Curated manifests may improve detection independently of application
        # releases, but their integrated resolvers remain the trusted source for
        # release metadata until registry signing keys are provisioned as TUF
        # targets and can be passed to the transfer verifier.
        from .resolvers import BUILTIN_RESOLVER_IDS, resolve_release

        if self.provider_id in BUILTIN_RESOLVER_IDS:
            return resolve_release(self.provider_id, identity)
        return self._resolve_declarative(identity)

    def _resolve_declarative(self, identity: IsoIdentity) -> ReleaseArtifact:
        hosts = frozenset(str(item).lower() for item in self.manifest["allowed_hosts"])
        client = SafeHttpClient(hosts)
        failures: list[str] = []
        for source in self.manifest["release_sources"]:
            if source.get("automatic_download", True) is False:
                continue
            if not _source_matches_identity(source["identity"], identity):
                continue
            try:
                return _resolve_source(client, hosts, source, identity)
            except ProviderError as error:
                failures.append(str(error))
        if failures:
            raise ProviderError(failures[-1])
        raise ProviderError("No automatic release source preserves this ISO variant.")

    @staticmethod
    def _validate(name: str, value: str | None, supported: tuple[str, ...]) -> None:
        if value is not None and value.lower() not in supported:
            raise ProviderError(f"Unsupported {name} for this provider: {value}")


def _resolve_source(
    client: SafeHttpClient,
    hosts: frozenset[str],
    source: dict[str, Any],
    identity: IsoIdentity,
) -> ReleaseArtifact:
    metadata_url = str(source["metadata_url"])
    metadata = client.metadata(metadata_url).decode("utf-8", errors="replace")
    candidates = _artifact_candidates(
        metadata, str(source["artifact_regex"]), source["identity"], identity
    )
    if not candidates:
        raise ProviderError("Official metadata contains no matching ISO variant.")
    filename, match = max(
        candidates,
        key=lambda item: _version_key(item[1].groupdict().get("version") or "0"),
    )
    groups = {key: value for key, value in match.groupdict().items() if value is not None}
    version = groups.get("version") or identity.version
    if version is None:
        raise ProviderError("Official metadata does not identify the release version.")
    values = _template_values(identity, filename, version, groups)
    url = _download_url(metadata, metadata_url, source["download"], filename, values)
    checksum_policy = source["verification"]["checksum"]
    algorithm = str(checksum_policy["algorithm"]).lower()
    checksum = _resolve_checksum(
        client, metadata, metadata_url, url, checksum_policy, filename, values, algorithm
    )
    signature_url, fingerprints = _signature(source, metadata_url, url, values)
    return ReleaseArtifact(
        version=version,
        build=groups.get("build"),
        filename=safe_filename(filename),
        download_url=url,
        size_bytes=_asset_size(metadata, filename),
        checksum_algorithm=algorithm,
        checksum=checksum,
        signature_url=signature_url,
        signer_fingerprints=fingerprints,
        allowed_hosts=hosts,
        identity=replace(identity, version=version, build=groups.get("build")),
    )


def _artifact_candidates(
    metadata: str,
    expression: str,
    identity_template: dict[str, Any],
    identity: IsoIdentity,
) -> list[tuple[str, re.Match[str]]]:
    artifact_pattern = regex.compile(expression, regex.IGNORECASE)
    names = set(re.findall(r"[A-Za-z0-9][A-Za-z0-9._+-]*\.iso", metadata, re.IGNORECASE))
    candidates: list[tuple[str, re.Match[str]]] = []
    for filename in names:
        try:
            match = artifact_pattern.fullmatch(filename, timeout=0.05)
        except TimeoutError:
            continue
        if match is not None and _candidate_identity_matches(
            match.groupdict(), identity_template, identity
        ):
            candidates.append((filename, match))
    return candidates


def _candidate_identity_matches(
    groups: dict[str, str | None], template: dict[str, Any], identity: IsoIdentity
) -> bool:
    for field in (
        "product_id",
        "edition",
        "flavor",
        "channel",
        "architecture",
        "language",
    ):
        configured = template.get(field)
        if isinstance(configured, str) and configured.startswith("$group:"):
            candidate = groups.get(configured.removeprefix("$group:"))
        else:
            candidate = configured
        if candidate is None:
            candidate = groups.get(field)
        actual = getattr(identity, field)
        if candidate is not None and (actual is None or str(candidate).lower() != actual.lower()):
            return False
    return True


def _source_matches_identity(template: dict[str, Any], identity: IsoIdentity) -> bool:
    for field in ("product_id", "edition", "flavor", "channel", "architecture", "language"):
        expected = template.get(field)
        if expected is None or (isinstance(expected, str) and expected.startswith("$group:")):
            continue
        actual = getattr(identity, field)
        if actual is None or str(expected).lower() != actual.lower():
            return False
    return True


def _template_values(
    identity: IsoIdentity, filename: str, version: str, groups: dict[str, str]
) -> dict[str, str]:
    return {
        "filename": filename,
        "stem": filename.removesuffix(".iso"),
        "version": version,
        "build": groups.get("build") or "",
        "product": identity.product_id,
        "product_id": identity.product_id,
        "edition": groups.get("edition") or identity.edition or "",
        "flavor": groups.get("flavor") or identity.flavor or "",
        "architecture": groups.get("architecture") or identity.architecture,
        "language": groups.get("language") or identity.language or "",
        "channel": identity.channel,
    }


def _download_url(
    metadata: str,
    metadata_url: str,
    policy: dict[str, Any],
    filename: str,
    values: dict[str, str],
) -> str:
    strategy = policy["strategy"]
    if strategy in {"url-template", "latest-redirect"}:
        return _format_url(str(policy["url_template"]), values)
    if strategy == "user-supplied":
        raise ProviderError("This provider requires an official user-supplied download link.")
    links = _metadata_links(metadata, metadata_url)
    if strategy == "release-asset":
        matching = [url for url in links if Path(urlsplit(url).path).name == filename]
    else:
        expression = regex.compile(str(policy["link_regex"]), regex.IGNORECASE)
        matching = []
        for url in links:
            try:
                matched = expression.fullmatch(url, timeout=0.05)
            except TimeoutError:
                continue
            if matched and Path(urlsplit(url).path).name == filename:
                matching.append(url)
    if not matching:
        raise ProviderError("Official metadata contains no download link for the selected ISO.")
    return matching[0]


def _resolve_checksum(
    client: SafeHttpClient,
    metadata: str,
    metadata_url: str,
    download_url: str,
    policy: dict[str, Any],
    filename: str,
    values: dict[str, str],
    algorithm: str,
) -> str:
    strategy = policy["strategy"]
    checksum_text = metadata
    if strategy == "sidecar":
        url = (
            _format_url(str(policy["url_template"]), values)
            if "url_template" in policy
            else download_url + str(policy.get("suffix", f".{algorithm}"))
        )
        checksum_text = client.metadata(url).decode("utf-8", errors="replace")
    elif strategy == "release-asset":
        suffix = str(policy.get("suffix", f".{algorithm}"))
        checksum_name = filename.removesuffix(".iso") + suffix
        links = _metadata_links(metadata, metadata_url)
        matches = [url for url in links if Path(urlsplit(url).path).name == checksum_name]
        if not matches:
            raise ProviderError("Official release lacks the required checksum asset.")
        checksum_text = client.metadata(matches[0]).decode("utf-8", errors="replace")
    elif strategy in {"release-digest", "embedded-json"}:
        digest = _embedded_digest(metadata, filename, algorithm)
        if digest is None:
            raise ProviderError("Official JSON metadata lacks the selected ISO digest.")
        return digest
    return _checksum(checksum_text, filename, algorithm)


def _signature(
    source: dict[str, Any], metadata_url: str, download_url: str, values: dict[str, str]
) -> tuple[str | None, tuple[str, ...]]:
    signature = source["verification"].get("signature")
    if signature is None:
        return None, ()
    fingerprints = tuple(str(item).upper() for item in signature["signer_fingerprints"])
    if signature["strategy"] == "signed-checksum-list":
        raise ProviderError(
            "Signed checksum metadata requires a provisioned trusted provider keyring."
        )
    if "url_template" in signature:
        url = _format_url(str(signature["url_template"]), values)
    elif signature["strategy"] == "sidecar":
        url = download_url + str(signature.get("suffix", ".sig"))
    else:
        url = metadata_url + str(signature.get("suffix", ".gpg"))
    return url, fingerprints


def _checksum(text: str, filename: str, algorithm: str) -> str:
    length = 64 if algorithm == "sha256" else 128
    escaped = re.escape(filename)
    patterns = (
        rf"^(?P<hash>[A-Fa-f0-9]{{{length}}})\s+[* ]?{escaped}\s*$",
        rf"{escaped}.{{0,500}}?(?P<hash>[A-Fa-f0-9]{{{length}}})",
    )
    for pattern in patterns:
        if match := re.search(pattern, text, re.MULTILINE | re.DOTALL):
            return match.group("hash").lower()
    stripped = text.strip()
    if re.fullmatch(rf"[A-Fa-f0-9]{{{length}}}(?:\s+.+)?", stripped):
        return stripped.split()[0].lower()
    raise ProviderError("Official metadata does not contain the selected ISO checksum.")


def _metadata_links(metadata: str, base_url: str) -> list[str]:
    links = re.findall(r"https://[^\s\"'<>]+", metadata)
    links.extend(
        urljoin(base_url, item) for item in re.findall(r"href=[\"']([^\"']+)[\"']", metadata)
    )
    try:
        payload = json.loads(metadata)
    except json.JSONDecodeError:
        return list(dict.fromkeys(links))

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and value.startswith("https://"):
            links.append(value)

    walk(payload)
    return list(dict.fromkeys(links))


def _asset_size(metadata: str, filename: str) -> int | None:
    try:
        payload = json.loads(metadata)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if isinstance(asset, dict) and asset.get("name") == filename:
            size = asset.get("size")
            return size if isinstance(size, int) and size >= 0 else None
    return None


def _embedded_digest(metadata: str, filename: str, algorithm: str) -> str | None:
    try:
        payload = json.loads(metadata)
    except json.JSONDecodeError:
        return None

    def walk(value: Any) -> str | None:
        if isinstance(value, dict):
            name = value.get("name")
            url = value.get("url") or value.get("browser_download_url")
            matches = name == filename or (
                isinstance(url, str) and Path(urlsplit(url).path).name == filename
            )
            if matches:
                digest = value.get("digest") or value.get(algorithm)
                if isinstance(digest, str):
                    digest = digest.removeprefix(f"{algorithm}:")
                    length = 64 if algorithm == "sha256" else 128
                    if re.fullmatch(rf"[A-Fa-f0-9]{{{length}}}", digest):
                        return digest.lower()
            for item in value.values():
                if result := walk(item):
                    return result
        elif isinstance(value, list):
            for item in value:
                if result := walk(item):
                    return result
        return None

    return walk(payload)


def _resolve_value(value: Any, match: re.Match[str]) -> Any:
    if isinstance(value, str) and value.startswith("$group:"):
        return match.groupdict().get(value.removeprefix("$group:"))
    return value


def _optional(value: Any, *, lower: bool = True) -> str | None:
    if value is None or value == "":
        return None
    result = str(value)
    return result.lower() if lower else result


def _architecture(value: str) -> str:
    return {
        "64bit": "x86_64",
        "64-bit": "x86_64",
        "x64": "x86_64",
        "x86-64": "x86_64",
        "all": "amd64",
    }.get(value.lower(), value.lower())


def _format_url(template: str, values: dict[str, str]) -> str:
    try:
        return template.format_map(values)
    except KeyError as error:
        raise ProviderError(
            f"Provider URL template references an unknown field: {error}"
        ) from error


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(item) for item in re.findall(r"\d+", value))
