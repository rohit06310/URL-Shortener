"""Edge Cache (CDN) and Load Balancer middleware."""

import itertools
import threading

from django.conf import settings
from django.core.cache import caches
from django.http import HttpResponseRedirect
from django.utils import timezone

from shortener.services.events import click_event_stream

_RESERVED_FIRST_SEGMENTS = {
    "",
    "admin",
    "shorten",
    "create",
    "analytics",
    "internal",
    "static",
    "favicon.ico",
}


class LoadBalancer:
    """Round-robin load balancer across configured Shortener service nodes."""

    def __init__(self):
        cfg = getattr(settings, "SHORTENER_CONFIG", {})
        nodes = cfg.get("BACKEND_NODES", ["shortener-node-1", "shortener-node-2"])
        self._cycle = itertools.cycle(nodes)
        self._lock = threading.Lock()

    def next_node(self) -> str:
        with self._lock:
            return next(self._cycle)


_load_balancer = LoadBalancer()


def _extract_short_key(path: str) -> str | None:
    stripped = path.strip("/")
    if not stripped or "/" in stripped:
        return None
    if stripped in _RESERVED_FIRST_SEGMENTS:
        return None
    return stripped


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


class EdgeCacheMiddleware:
    """Simulates CDN Edge Cache in front of the Load Balancer and Shortener Service."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        key = _extract_short_key(request.path) if request.method == "GET" else None
        edge_cache = caches["edge"]

        if key is not None:
            cached = edge_cache.get(f"edge:{key}")
            if cached is not None:
                expires_at = cached.get("expires_at")
                if expires_at is None or expires_at > timezone.now():
                    click_event_stream.publish(
                        key=key,
                        referer=request.META.get("HTTP_REFERER", ""),
                        user_agent=request.META.get("HTTP_USER_AGENT", ""),
                        client_ip=_client_ip(request),
                    )
                    response = HttpResponseRedirect(cached["link"])
                    response["X-Edge-Cache"] = "HIT"
                    return response
                edge_cache.delete(f"edge:{key}")

        # Edge cache miss or non-redirect route: forward through Load Balancer.
        node = _load_balancer.next_node()
        request.lb_node = node
        response = self.get_response(request)
        response["X-Served-By"] = node

        if key is not None:
            response["X-Edge-Cache"] = "MISS"
            if response.status_code == 302 and response.get("X-Shortener-Cacheable") == "1":
                cfg = getattr(settings, "SHORTENER_CONFIG", {})
                edge_ttl = cfg.get("EDGE_CACHE_TTL_SECONDS", 60)
                expires_at = getattr(response, "_shortener_expires_at", None)
                if expires_at is not None:
                    remaining = int((expires_at - timezone.now()).total_seconds())
                    edge_ttl = max(0, min(edge_ttl, remaining))
                if edge_ttl > 0:
                    edge_cache.set(
                        f"edge:{key}",
                        {"link": response["Location"], "expires_at": expires_at},
                        timeout=edge_ttl,
                    )
                    response["Cache-Control"] = f"public, max-age={edge_ttl}"

        return response
