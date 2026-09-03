from pathlib import Path

from ..config import load_settings
from ..security import SecurityError, load_and_validate_manifest
from .base import Provider, ProviderCapabilities, ProviderError
from .builtin import BUILTIN_PROVIDERS
from .manifest import ManifestProvider


def provider_map(*, refresh: bool = False) -> dict[str, Provider]:
    providers = {provider.provider_id: provider for provider in BUILTIN_PROVIDERS}
    from ..registry_client import load_registry

    settings = load_settings()
    for manifest in load_registry(refresh=refresh and settings.registry_updates).manifests:
        provider = ManifestProvider(manifest, origin="registry")
        providers[provider.provider_id] = provider
    for configured in settings.local_manifests:
        path = Path(configured)
        if path.is_symlink():
            raise SecurityError(f"Local manifest must not be a symlink: {path}")
        manifest = load_and_validate_manifest(path)
        provider = ManifestProvider(manifest, origin="custom")
        if provider.provider_id in providers:
            raise SecurityError(
                f"Local manifest cannot override a curated provider: {provider.provider_id}"
            )
        providers[provider.provider_id] = provider
    return providers


__all__ = [
    "BUILTIN_PROVIDERS",
    "ManifestProvider",
    "Provider",
    "ProviderCapabilities",
    "ProviderError",
    "provider_map",
]
