"""Shared API dependencies: crypto provider, settings."""

from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.crypto.key_provider import DatabaseKeyProvider

_provider: DatabaseKeyProvider | None = None


def get_provider() -> DatabaseKeyProvider:
    global _provider
    if _provider is None:
        _provider = DatabaseKeyProvider(get_settings())
    return _provider


ProviderDep = Annotated[DatabaseKeyProvider, Depends(get_provider)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
