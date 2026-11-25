"""Shortener service HTTP views."""

import json

from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from shortener.models import ClickEvent, Url
from shortener.services.analytics import ClickAnalyticsService
from shortener.services.cleanup import run_expiry_cleanup
from shortener.services.events import click_event_stream
from shortener.services.shortener import ShortenerService


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def index(request):
    """Web client home page."""
    return render(request, "index.html")


@csrf_exempt
@require_POST
def shorten(request):
    """Creator API endpoint: POST /shorten -> JSON {key, short_url, link, expires_at}."""
    link = None
    ttl_seconds = None

    if request.content_type and "application/json" in request.content_type:
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body."}, status=400)
        link = body.get("url") or body.get("link")
        raw_ttl = body.get("ttl_seconds")
    else:
        link = request.POST.get("url") or request.POST.get("link")
        raw_ttl = request.POST.get("ttl_seconds")

    if raw_ttl not in (None, ""):
        try:
            ttl_seconds = int(raw_ttl)
        except (TypeError, ValueError):
            return JsonResponse({"error": "ttl_seconds must be an integer."}, status=400)

    try:
        record = ShortenerService.shorten(link=link, ttl_seconds=ttl_seconds)
    except ValidationError as exc:
        return JsonResponse({"error": "; ".join(exc.messages)}, status=400)

    scheme = request.scheme
    host = request.get_host()
    return JsonResponse(
        {
            "key": record.uuid,
            "short_url": f"{scheme}://{host}/{record.uuid}",
            "link": record.link,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        },
        status=201,
    )


def create(request):
    """Legacy form/AJAX endpoint kept for backward compatibility."""
    if request.method == "POST":
        link = request.POST.get("link", "")
        try:
            record = ShortenerService.shorten(link=link)
        except ValidationError as exc:
            return HttpResponse("; ".join(exc.messages), status=400)
        return HttpResponse(record.uuid)
    return HttpResponse("Nothings Here")


@require_GET
def url(request, url_id: str):
    """Visitor redirect endpoint: GET /{key}."""
    destination, status, expires_at = ShortenerService.resolve(url_id)
    if status in ("HIT", "MISS") and destination:
        click_event_stream.publish(
            key=url_id,
            referer=request.META.get("HTTP_REFERER", ""),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            client_ip=_client_ip(request),
        )
        response = redirect(destination)
        response["X-Hot-Cache"] = status
        response["X-Shortener-Cacheable"] = "1"
        response._shortener_expires_at = expires_at
        return response

    if status == "EXPIRED":
        return HttpResponse("This short link has expired.", status=410)

    return HttpResponse("Short link not found.", status=404)


@require_GET
def analytics(request, url_id: str):
    """Click analytics endpoint: GET /analytics/{key}."""
    exists = Url.objects.filter(uuid=url_id).exists() or ClickEvent.objects.filter(key=url_id).exists()
    if not exists:
        return JsonResponse({"error": "Short link not found."}, status=404)
    return JsonResponse(ClickAnalyticsService.get_key_analytics(url_id))


@csrf_exempt
@require_POST
def cleanup(request):
    """Internal trigger for the Expiry Cleanup serverless function."""
    deleted = run_expiry_cleanup()
    return JsonResponse({"deleted": deleted})
