from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tuf.ngclient.fetcher import FetcherInterface

from .config import cache_path
from .security import SecurityError, load_and_validate_manifest

REGISTRY_METADATA_URL = "https://unfortunatelyalex.github.io/ventoy-depot-registry/metadata/"
REGISTRY_TARGET_URL = "https://unfortunatelyalex.github.io/ventoy-depot-registry/targets/"
CHECK_INTERVAL = timedelta(days=1)


@dataclass(frozen=True)
class RegistrySnapshot:
    manifests: tuple[dict[str, Any], ...]
    origin: str
    warning: str | None = None


def bundled_root_path() -> Path:
    return Path(__file__).with_name("registry") / "root.json"


def load_registry(*, refresh: bool = False, root: Path | None = None) -> RegistrySnapshot:
    """Load only TUF-verified remote manifests, otherwise retain built-in providers."""
    trust_root = root or bundled_root_path()
    if not trust_root.is_file():
        return RegistrySnapshot((), "bundled", "Remote registry has no provisioned trust root.")
    directory = cache_path() / "registry"
    refresh_warning = None
    if refresh and _refresh_due(directory):
        try:
            _refresh(directory, trust_root)
        except Exception as error:
            refresh_warning = f"Registry refresh failed; using verified cache: {error}"
    try:
        manifests = _load_cached(directory, trust_root)
    except Exception as error:
        return RegistrySnapshot((), "bundled", f"Remote registry rejected: {error}")
    if not manifests:
        return RegistrySnapshot((), "bundled", "No valid cached registry is available.")
    return RegistrySnapshot(tuple(manifests), "tuf", refresh_warning)


def _refresh_due(directory: Path, now: datetime | None = None) -> bool:
    if any(
        not (directory / "metadata" / name).is_file()
        for name in ("timestamp.json", "snapshot.json", "targets.json")
    ):
        return True
    checked = _read_state(directory).get("checked_at")
    if not isinstance(checked, str):
        return True
    try:
        last = datetime.fromisoformat(checked)
    except ValueError:
        return True
    current = now or datetime.now(UTC)
    return current - last.astimezone(UTC) >= CHECK_INTERVAL


def _refresh(directory: Path, trust_root: Path) -> None:
    from tuf.ngclient import Updater

    metadata = directory / "metadata"
    targets = directory / "targets"
    metadata.mkdir(parents=True, exist_ok=True)
    targets.mkdir(parents=True, exist_ok=True)
    updater = Updater(
        str(metadata),
        REGISTRY_METADATA_URL,
        str(targets),
        REGISTRY_TARGET_URL,
        bootstrap=trust_root.read_bytes(),
    )
    updater.refresh()
    index_info = updater.get_targetinfo("providers/index.json")
    if index_info is None:
        raise SecurityError("Signed registry index is missing.")
    index_path = Path(updater.download_target(index_info))
    index = _read_json(index_path)
    provider_ids = index.get("providers")
    if index.get("schema_version") != 1 or not isinstance(provider_ids, list):
        raise SecurityError("Signed registry index is invalid.")
    for provider_id in provider_ids:
        if not isinstance(provider_id, str) or not provider_id:
            raise SecurityError("Signed registry index contains an invalid provider id.")
        target_name = f"providers/{provider_id}.json"
        target_info = updater.get_targetinfo(target_name)
        if target_info is None:
            raise SecurityError(f"Signed registry target is missing: {target_name}")
        path = Path(updater.download_target(target_info))
        manifest = load_and_validate_manifest(path)
        if manifest["provider_id"] != provider_id:
            raise SecurityError("Registry target name does not match its provider id.")
    _write_state(directory)


def _load_cached(directory: Path, trust_root: Path) -> list[dict[str, Any]]:
    updater = _offline_updater(directory, trust_root)
    updater.refresh()
    index_info = updater.get_targetinfo("providers/index.json")
    if index_info is None:
        raise SecurityError("Signed cached registry index is missing.")
    manifests: list[dict[str, Any]] = []
    target_root = (directory / "targets").resolve()
    index_path = (target_root / "providers" / "index.json").resolve()
    _verify_cached_target(index_info, index_path, target_root)
    index = _read_json(index_path)
    provider_ids = index.get("providers")
    if index.get("schema_version") != 1 or not isinstance(provider_ids, list):
        raise SecurityError("Signed cached registry index is invalid.")
    for provider_id in provider_ids:
        if not isinstance(provider_id, str) or not provider_id:
            raise SecurityError("Signed cached registry index contains an invalid provider id.")
        relative = f"providers/{provider_id}.json"
        target_info = updater.get_targetinfo(relative)
        if target_info is None:
            raise SecurityError(f"Signed cached registry target is missing: {relative}")
        path = (target_root / relative).resolve()
        _verify_cached_target(target_info, path, target_root)
        manifest = load_and_validate_manifest(path)
        if manifest["provider_id"] != provider_id:
            raise SecurityError("Cached registry target name does not match its provider id.")
        manifests.append(manifest)
    return manifests


def _verify_cached_target(target_info: Any, path: Path, target_root: Path) -> None:
    try:
        path.relative_to(target_root)
    except ValueError as error:
        raise SecurityError("Registry cache path escapes its target directory.") from error
    try:
        target_info.verify_length_and_hashes(path.read_bytes())
    except Exception as error:
        raise SecurityError(
            f"Cached registry target failed TUF verification: {path.name}"
        ) from error


def _offline_updater(directory: Path, trust_root: Path) -> Any:
    from tuf.ngclient import Updater

    metadata = directory / "metadata"
    targets = directory / "targets"
    return Updater(
        str(metadata),
        "https://offline.invalid/metadata/",
        str(targets),
        "https://offline.invalid/targets/",
        fetcher=_CachedMetadataFetcher(metadata),
        bootstrap=trust_root.read_bytes(),
    )


class _CachedMetadataFetcher(FetcherInterface):
    """Feed cached metadata through python-tuf's regular verification workflow."""

    def __init__(self, metadata: Path) -> None:
        self.metadata = metadata

    def _fetch(self, url: str) -> Iterator[bytes]:
        name = Path(urlsplit(url).path).name
        if match := re.fullmatch(r"\d+\.(.+\.json)", name):
            path = (
                self.metadata / "root_history" / name
                if match.group(1) == "root.json"
                else self.metadata / match.group(1)
            )
        else:
            path = self.metadata / name
        if not path.is_file():
            from tuf.api.exceptions import DownloadHTTPError

            raise DownloadHTTPError(f"Cached metadata is missing: {name}", 404)
        yield path.read_bytes()


def _read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 1024 * 1024:
        raise SecurityError("Registry index exceeds the metadata limit.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SecurityError("Registry index must be an object.")
    return value


def _read_state(directory: Path) -> dict[str, Any]:
    try:
        value = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_state(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="state.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(
                {
                    "schema_version": 1,
                    "checked_at": datetime.now(UTC).isoformat(),
                },
                output,
                indent=2,
                sort_keys=True,
            )
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, directory / "state.json")
    except Exception:
        Path(name).unlink(missing_ok=True)
        raise
