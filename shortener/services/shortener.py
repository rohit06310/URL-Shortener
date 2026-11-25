"""Core Shortener Application Service."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils import timezone

from shortener.models import Url
from shortener.services.cache import HotLinksCache
from shortener.services.keygen import default_kgs
from shortener.services.link_store import LinkStore

_url_validator = URLValidator(schemes=["http", "https"])


class ShortenerService:
    """Coordinates KGS, LinkStore, and HotLinksCache for URL shortening and resolution."""

    @staticmethod
    def validate_url(link: str) -> str:
        """Validate that link is an http/https URL and return the stripped string."""
        cleaned = (link or "").strip()
        _url_validator(cleaned)
        return cleaned

    @classmethod
    def shorten(cls, link: str, ttl_seconds: int | None = None) -> Url:
        """Validate URL, allocate a key via KGS, persist in LinkStore, and warm HotLinksCache."""
        cleaned = cls.validate_url(link)
        expires_at = None
        if ttl_seconds is not None:
            if ttl_seconds <= 0:
                raise ValidationError("ttl_seconds must be a positive integer.")
            expires_at = timezone.now() + timedelta(seconds=ttl_seconds)

        key = default_kgs.next_key()
        record = LinkStore.put(key=key, link=cleaned, expires_at=expires_at)
        HotLinksCache.set(key=key, link=cleaned, expires_at=expires_at)
        return record

    @staticmethod
    def resolve(key: str) -> tuple[str | None, str, object]:
        """Resolve a short key via HotLinksCache -> LinkStore.

        Returns (destination_url | None, status, expires_at).
        status is one of: 'HIT', 'MISS', 'EXPIRED', 'NOT_FOUND'.
        """
        cached = HotLinksCache.get(key)
        if cached is not None:
            return cached["link"], "HIT", cached.get("expires_at")

        record = LinkStore.get(key)
        if record is None:
            return None, "NOT_FOUND", None

        if record.is_expired():
            return None, "EXPIRED", record.expires_at

        HotLinksCache.set(key=key, link=record.link, expires_at=record.expires_at)
        return record.link, "MISS", record.expires_at
