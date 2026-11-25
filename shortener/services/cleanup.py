"""Serverless-style Expiry Cleanup job for removing expired links and evicting caches."""

from django.core.cache import caches
from django.utils import timezone

from shortener.services.cache import HotLinksCache
from shortener.services.link_store import LinkStore


def run_expiry_cleanup(now=None) -> int:
    """Delete expired links from LinkStore and invalidate HotLinks + Edge caches."""
    current = now or timezone.now()
    deleted_keys = LinkStore.delete_expired(now=current)
    edge_cache = caches["edge"]
    for key in deleted_keys:
        HotLinksCache.delete(key)
        edge_cache.delete(f"edge:{key}")
    return len(deleted_keys)
