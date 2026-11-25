from django.db import models
from django.utils import timezone


class Url(models.Model):
    """Link store record mapping a short key to its destination URL."""

    link = models.CharField(max_length=2048)
    uuid = models.CharField(max_length=16, unique=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    def is_expired(self, now=None) -> bool:
        """Return True if the link has a TTL that has elapsed."""
        if self.expires_at is None:
            return False
        current = now or timezone.now()
        return self.expires_at <= current

    def __str__(self) -> str:
        return f"{self.uuid} -> {self.link[:32]}"


class KeyRange(models.Model):
    """Coordination/config record for non-overlapping ID ranges claimed by KGS nodes."""

    start = models.BigIntegerField()
    end = models.BigIntegerField()
    node_id = models.CharField(max_length=64)
    claimed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-end"]

    def __str__(self) -> str:
        return f"[{self.start}, {self.end}] ({self.node_id})"


class ClickEvent(models.Model):
    """Analytics/OLAP record for link redirect events."""

    key = models.CharField(max_length=16, db_index=True)
    clicked_at = models.DateTimeField(db_index=True)
    referer = models.CharField(max_length=512, blank=True, default="")
    user_agent = models.CharField(max_length=512, blank=True, default="")
    ip_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["-clicked_at"]

    def __str__(self) -> str:
        return f"{self.key} @ {self.clicked_at.isoformat()}"
