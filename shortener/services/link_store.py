"""Key-Value / Document Link Store backed by Django ORM."""

from django.utils import timezone

from shortener.models import Url


class LinkStore:
    """Persistent storage interface for short-key -> URL mappings."""

    @staticmethod
    def get(key: str) -> Url | None:
        """Return the Url record for a key, or None if not found."""
        return Url.objects.filter(uuid=key).first()

    @staticmethod
    def put(key: str, link: str, expires_at=None) -> Url:
        """Persist a new short-key -> URL mapping."""
        return Url.objects.create(uuid=key, link=link, expires_at=expires_at)

    @staticmethod
    def delete_expired(now=None) -> list[str]:
        """Delete all expired links and return the deleted keys."""
        current = now or timezone.now()
        expired_qs = Url.objects.filter(expires_at__isnull=False, expires_at__lte=current)
        keys = list(expired_qs.values_list("uuid", flat=True))
        if keys:
            expired_qs.delete()
        return keys
