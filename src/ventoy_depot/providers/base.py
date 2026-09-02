from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from ..models import DetectedIso, IsoIdentity, ReleaseArtifact, is_newer_version


class ProviderError(RuntimeError):
    """A provider could not safely resolve a matching official release."""


@dataclass(frozen=True)
class ProviderCapabilities:
    editions: tuple[str, ...]
    architectures: tuple[str, ...]
    languages: tuple[str, ...]
    channels: tuple[str, ...]


class Provider(ABC):
    provider_id: str
    display_name: str
    capabilities: ProviderCapabilities

    @abstractmethod
    def detect(self, path: Path) -> DetectedIso | None:
        """Identify an ISO without modifying it."""

    @abstractmethod
    def resolve(self, identity: IsoIdentity) -> ReleaseArtifact:
        """Resolve the latest artifact preserving every variant dimension."""

    def is_newer(self, artifact: ReleaseArtifact, identity: IsoIdentity) -> bool:
        return is_newer_version(artifact.version, identity.version)

    def validate_binding(self, current: IsoIdentity, target: IsoIdentity) -> None:
        if current.variant_key() != target.variant_key():
            raise ProviderError("Provider attempted to change an ISO variant without consent.")
