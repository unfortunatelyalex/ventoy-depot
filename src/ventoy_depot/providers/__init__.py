from .base import Provider, ProviderCapabilities, ProviderError
from .builtin import BUILTIN_PROVIDERS


def provider_map() -> dict[str, Provider]:
    return {provider.provider_id: provider for provider in BUILTIN_PROVIDERS}


__all__ = ["BUILTIN_PROVIDERS", "Provider", "ProviderCapabilities", "ProviderError", "provider_map"]
