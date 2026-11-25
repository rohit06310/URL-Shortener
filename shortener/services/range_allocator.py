"""Coordination / Config service for allocating non-overlapping key ranges."""

from django.conf import settings
from django.db import transaction

from shortener.models import KeyRange


class RangeAllocator:
    """Allocates disjoint integer ranges to Key Generation Service instances."""

    @staticmethod
    def claim_range(node_id: str | None = None, range_size: int | None = None) -> tuple[int, int]:
        """Atomically claim the next available [start, end] ID range for a KGS node."""
        cfg = getattr(settings, "SHORTENER_CONFIG", {})
        size = range_size or cfg.get("RANGE_SIZE", 1000)
        initial_start = cfg.get("RANGE_START", 100000)
        owner = node_id or cfg.get("NODE_ID", "shortener-node-1")

        with transaction.atomic():
            latest = KeyRange.objects.select_for_update().order_by("-end").first()
            start = (latest.end + 1) if latest else initial_start
            end = start + size - 1
            KeyRange.objects.create(start=start, end=end, node_id=owner)
            return start, end
