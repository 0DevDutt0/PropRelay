"""Safe read-only caching layer for static catalog entities and query results.

STRICT CONSTRAINTS (TDR-044):
- Safe to cache: Immutable property details, catalog searches (bounded TTL).
- STRICTLY PROHIBITED: Showing slot availability (subject to concurrency booking races),
  booking creations, policy authorizations, lead mutations, confirmation states.
"""

from __future__ import annotations

import time
from typing import Any


class SafeReadOnlyCache:
    """Thread-safe bounded in-memory cache for read-only catalog data."""

    def __init__(
        self,
        property_ttl_seconds: float = 300.0,
        search_ttl_seconds: float = 60.0,
        max_entries: int = 128,
    ) -> None:
        self._property_ttl = property_ttl_seconds
        self._search_ttl = search_ttl_seconds
        self._max_entries = max_entries

        # In-memory storage: key -> (value, expire_timestamp)
        self._property_cache: dict[str, tuple[Any, float]] = {}
        self._search_cache: dict[str, tuple[Any, float]] = {}

        # Telemetry
        self.hits: int = 0
        self.misses: int = 0
        self.evictions: int = 0

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 3) if total > 0 else 0.0

    def get_property(self, property_id: str) -> Any | None:
        """Retrieve cached property details if not expired."""
        now = time.monotonic()
        if property_id in self._property_cache:
            val, exp = self._property_cache[property_id]
            if now < exp:
                self.hits += 1
                return val
            # Expired
            del self._property_cache[property_id]
        self.misses += 1
        return None

    def put_property(self, property_id: str, property_obj: Any) -> None:
        """Cache property details with TTL."""
        if len(self._property_cache) >= self._max_entries:
            # Simple eviction: drop the first item
            first_key = next(iter(self._property_cache))
            del self._property_cache[first_key]
            self.evictions += 1

        self._property_cache[property_id] = (
            property_obj,
            time.monotonic() + self._property_ttl,
        )

    def get_search_results(self, search_key: str) -> list[Any] | None:
        """Retrieve cached search result list if not expired."""
        now = time.monotonic()
        if search_key in self._search_cache:
            val, exp = self._search_cache[search_key]
            if now < exp:
                self.hits += 1
                return list(val)
            del self._search_cache[search_key]
        self.misses += 1
        return None

    def put_search_results(self, search_key: str, results: list[Any]) -> None:
        """Cache search result list with bounded TTL."""
        if len(self._search_cache) >= self._max_entries:
            first_key = next(iter(self._search_cache))
            del self._search_cache[first_key]
            self.evictions += 1

        self._search_cache[search_key] = (
            list(results),
            time.monotonic() + self._search_ttl,
        )

    def clear(self) -> None:
        """Clear all cached entries."""
        self._property_cache.clear()
        self._search_cache.clear()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
