"""In-memory hot links cache abstraction."""

from django.conf import settings
from django.core.cache import caches
from django.utils import timezone


class HotLinksCache:
    """Caches frequently accessed short-key -> destination mappings."""

    CACHE_ALIAS = "default"
    KEY_PREFIX = "link:"

    @classmethod
    def _cache(cls):
        return caches[cls.CACHE_ALIAS]

    @classmethod
    def _ttl_for(cls, expires_at=None) -> int | None:
        cfg = getattr(settings, "SHORTENER_CONFIG", {})
        default_ttl = cfg.get("HOT_CACHE_TTL_SECONDS", 300)
        if expires_at is None:
            return default_ttl
        remaining = int((expires_at - timezone.now()).total_seconds())
        if remaining <= 0:
            return 0
        return min(default_ttl, remaining)

    @classmethod
    def get(cls, key: str) -> dict | None:
        """Fetch cached link payload {'link': str, 'expires_at': datetime | None}."""
        payload = cls._cache().get(f"{cls.KEY_PREFIX}{key}")
        if payload is None:
            return None
        expires_at = payload.get("expires_at")
        if expires_at is not None and expires_at <= timezone.now():
            cls.delete(key)
            return None
        return payload

    @classmethod
    def set(cls, key: str, link: str, expires_at=None) -> None:
        """Store link payload in hot links cache with TTL bounded by expiry."""
        ttl = cls._ttl_for(expires_at)
        if ttl == 0:
            return
        cls._cache().set(
            f"{cls.KEY_PREFIX}{key}",
            {"link": link, "expires_at": expires_at},
            timeout=ttl,
        )

    @classmethod
    def delete(cls, key: str) -> None:
        """Evict a short key from the hot links cache."""
        cls._cache().delete(f"{cls.KEY_PREFIX}{key}")
