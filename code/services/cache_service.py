"""Cache service skeleton."""

from __future__ import annotations

from typing import Any

from config import Settings


class CacheService:
    """Content-addressed cache facade."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.resolve_path(self.settings.cache_dir).mkdir(
            parents=True, exist_ok=True
        )

    def get(self, namespace: str, key: str) -> dict[str, Any] | None:
        """Fetch a cached record if present."""
        _ = (namespace, key)
        return None

    def set(self, namespace: str, key: str, value: dict[str, Any]) -> None:
        """Persist a cached record."""
        _ = (namespace, key, value)
