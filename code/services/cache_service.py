"""In-memory content-addressed cache service."""

from __future__ import annotations

from typing import Any

from config import Settings


class CacheService:
    """Content-addressed cache backed by an in-memory dict.

    Survives the lifetime of the process.  Not persisted across runs.
    Cache directory on disk is still created for potential future disk-backed
    storage.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.resolve_path(self.settings.cache_dir).mkdir(
            parents=True, exist_ok=True
        )
        self._cache: dict[str, dict[str, Any]] = {}

    def get(self, namespace: str, key: str) -> dict[str, Any] | None:
        """Fetch a cached record if present."""
        ns = self._cache.get(namespace)
        if ns is None:
            return None
        return ns.get(key)

    def set(self, namespace: str, key: str, value: dict[str, Any]) -> None:
        """Persist a cached record."""
        if namespace not in self._cache:
            self._cache[namespace] = {}
        self._cache[namespace][key] = value
