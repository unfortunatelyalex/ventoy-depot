from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

from platformdirs import user_cache_path, user_config_path


@dataclass(frozen=True)
class Settings:
    language: str = "en"
    registry_updates: bool = True
    download_cache: bool = True
    proxy: str | None = None
    metadata_parallelism: int = 4
    default_action: str = "add"
    local_manifests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.language not in {"en", "de"}:
            raise ValueError("Language must be 'en' or 'de'.")
        if not 1 <= self.metadata_parallelism <= 16:
            raise ValueError("Metadata parallelism must be between 1 and 16.")
        if self.default_action not in {"add", "skip"}:
            raise ValueError("The safe default action must be add or skip.")
        if self.proxy is not None:
            parsed = urlsplit(self.proxy)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Proxy must be a credential-free HTTP or HTTPS URL.")
        if len(self.local_manifests) != len(set(self.local_manifests)):
            raise ValueError("Local manifest paths must be unique.")
        if any(not item or not Path(item).is_absolute() for item in self.local_manifests):
            raise ValueError("Local manifest paths must be non-empty absolute paths.")


def config_path() -> Path:
    return user_config_path("ventoy-depot", ensure_exists=True) / "config.json"


def cache_path() -> Path:
    return user_cache_path("ventoy-depot", ensure_exists=True)


def load_settings(path: Path | None = None) -> Settings:
    source = path or config_path()
    if not source.exists():
        return Settings()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.pop("schema_version", None) != 1:
        raise ValueError("Unsupported settings schema version.")
    local_manifests = payload.get("local_manifests", ())
    if not isinstance(local_manifests, list) or any(
        not isinstance(item, str) for item in local_manifests
    ):
        raise ValueError("Local manifests must be a list of absolute paths.")
    payload["local_manifests"] = tuple(local_manifests)
    return Settings(**payload)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    destination = path or config_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="config.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"schema_version": 1, **asdict(settings)}, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise
