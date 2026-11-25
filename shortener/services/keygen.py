"""Key Generation Service (KGS) dispensing Base62 keys from claimed ranges."""

import threading

from django.conf import settings

from shortener.models import Url
from shortener.services.range_allocator import RangeAllocator

BASE62_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def encode_base62(num: int) -> str:
    """Encode a non-negative integer into a Base62 string."""
    if num == 0:
        return BASE62_ALPHABET[0]
    chars = []
    base = len(BASE62_ALPHABET)
    while num > 0:
        num, rem = divmod(num, base)
        chars.append(BASE62_ALPHABET[rem])
    return "".join(reversed(chars))


class KeyGenerationService:
    """Thread-safe key generator backed by RangeAllocator."""

    def __init__(self, node_id: str | None = None):
        cfg = getattr(settings, "SHORTENER_CONFIG", {})
        self.node_id = node_id or cfg.get("NODE_ID", "shortener-node-1")
        self._lock = threading.Lock()
        self._current: int | None = None
        self._end: int | None = None

    def next_key(self) -> str:
        """Return the next unique Base62 short key, claiming a new range if exhausted."""
        with self._lock:
            while True:
                if self._current is None or self._end is None or self._current > self._end:
                    self._current, self._end = RangeAllocator.claim_range(node_id=self.node_id)
                candidate = encode_base62(self._current)
                self._current += 1
                if not Url.objects.filter(uuid=candidate).exists():
                    return candidate

    def reset(self) -> None:
        """Reset in-memory range state (useful in tests)."""
        with self._lock:
            self._current = None
            self._end = None


default_kgs = KeyGenerationService()
