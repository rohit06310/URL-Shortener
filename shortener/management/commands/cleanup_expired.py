"""Management command to run the Expiry Cleanup serverless function."""

from django.core.management.base import BaseCommand

from shortener.services.cleanup import run_expiry_cleanup


class Command(BaseCommand):
    help = "Delete expired short links from LinkStore and evict them from caches."

    def handle(self, *args, **options):
        deleted = run_expiry_cleanup()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired link(s)."))
