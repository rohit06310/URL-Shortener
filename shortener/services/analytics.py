"""Data Warehouse / OLAP Click Analytics service."""

from django.db.models import Count
from django.db.models.functions import TruncDate

from shortener.models import ClickEvent


class ClickAnalyticsService:
    """Stores and aggregates click events for short links."""

    @staticmethod
    def record_clicks(events: list[dict]) -> int:
        """Persist a batch of click event payloads."""
        if not events:
            return 0
        objs = [
            ClickEvent(
                key=ev["key"],
                clicked_at=ev["clicked_at"],
                referer=(ev.get("referer") or "")[:512],
                user_agent=(ev.get("user_agent") or "")[:512],
                ip_hash=(ev.get("ip_hash") or "")[:64],
            )
            for ev in events
        ]
        ClickEvent.objects.bulk_create(objs)
        return len(objs)

    @staticmethod
    def get_key_analytics(key: str) -> dict:
        """Return aggregated OLAP-style analytics for a short key."""
        qs = ClickEvent.objects.filter(key=key)
        total_clicks = qs.count()
        by_day_rows = (
            qs.annotate(day=TruncDate("clicked_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        clicks_by_day = [
            {"date": row["day"].isoformat() if row["day"] else None, "clicks": row["count"]}
            for row in by_day_rows
        ]
        top_referers = list(
            qs.exclude(referer="")
            .values("referer")
            .annotate(clicks=Count("id"))
            .order_by("-clicks")[:5]
        )
        latest = qs.order_by("-clicked_at").first()
        return {
            "key": key,
            "total_clicks": total_clicks,
            "last_clicked_at": latest.clicked_at.isoformat() if latest else None,
            "clicks_by_day": clicks_by_day,
            "top_referers": top_referers,
        }
