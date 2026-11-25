"""Async Click Events streaming pipeline."""

import hashlib
import queue
import sys
import threading

from django.db import close_old_connections
from django.utils import timezone

from shortener.services.analytics import ClickAnalyticsService


class ClickEventStream:
    """Non-blocking event queue that streams click events to ClickAnalyticsService."""

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._consume_loop,
                    name="click-event-consumer",
                    daemon=True,
                )
                self._worker.start()

    def _consume_loop(self) -> None:
        while True:
            item = self._queue.get()
            batch = [item]
            while len(batch) < 50:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            try:
                close_old_connections()
                ClickAnalyticsService.record_clicks(batch)
            except Exception:
                # Never crash the background stream consumer.
                pass
            finally:
                for _ in batch:
                    self._queue.task_done()

    def publish(self, key: str, referer: str = "", user_agent: str = "", client_ip: str = "") -> None:
        """Publish a click event without blocking the redirect response."""
        ip_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:16] if client_ip else ""
        payload = {
            "key": key,
            "clicked_at": timezone.now(),
            "referer": referer,
            "user_agent": user_agent,
            "ip_hash": ip_hash,
        }
        # In Django test runs using in-memory SQLite, write inline to avoid cross-thread SQLite locks.
        if "test" in sys.argv:
            ClickAnalyticsService.record_clicks([payload])
            return
        self._ensure_worker()
        self._queue.put(payload)

    def flush(self) -> None:
        """Wait until all queued click events have been processed."""
        self._queue.join()


click_event_stream = ClickEventStream()
