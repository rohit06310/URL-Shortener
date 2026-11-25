import json
from datetime import timedelta

from django.core.cache import caches
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from shortener.models import ClickEvent, KeyRange, Url
from shortener.services.cleanup import run_expiry_cleanup
from shortener.services.keygen import KeyGenerationService, default_kgs, encode_base62
from shortener.services.range_allocator import RangeAllocator


class RangeAllocatorAndKeygenTests(TestCase):
    def setUp(self):
        default_kgs.reset()

    @override_settings(SHORTENER_CONFIG={"RANGE_SIZE": 3, "RANGE_START": 100, "NODE_ID": "node-a"})
    def test_range_allocator_claims_disjoint_ranges_and_rolls_over(self):
        kgs = KeyGenerationService(node_id="node-a")
        keys = [kgs.next_key() for _ in range(4)]
        self.assertEqual(keys, [encode_base62(100), encode_base62(101), encode_base62(102), encode_base62(103)])
        self.assertEqual(KeyRange.objects.count(), 2)
        ranges = list(KeyRange.objects.order_by("start").values_list("start", "end"))
        self.assertEqual(ranges, [(100, 102), (103, 105)])

    def test_two_allocators_get_non_overlapping_ranges(self):
        r1 = RangeAllocator.claim_range(node_id="node-1", range_size=50)
        r2 = RangeAllocator.claim_range(node_id="node-2", range_size=50)
        self.assertEqual(r1[1] + 1, r2[0])


class UrlShortenerSystemDesignTests(TestCase):
    def setUp(self):
        self.client = Client()
        default_kgs.reset()
        caches["default"].clear()
        caches["edge"].clear()

    def test_shorten_edge_cache_redirect_and_analytics_flow(self):
        resp = self.client.post(
            "/shorten",
            data=json.dumps({"url": "https://example.com/docs"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        payload = resp.json()
        key = payload["key"]
        self.assertEqual(payload["link"], "https://example.com/docs")

        # First GET /{key}: Edge cache MISS -> Load balancer -> Shortener service (HotLinksCache HIT)
        r1 = self.client.get(f"/{key}", HTTP_REFERER="https://news.ycombinator.com")
        self.assertEqual(r1.status_code, 302)
        self.assertEqual(r1["Location"], "https://example.com/docs")
        self.assertEqual(r1["X-Edge-Cache"], "MISS")
        self.assertIn("X-Served-By", r1)

        # Second GET /{key}: Edge cache HIT directly
        r2 = self.client.get(f"/{key}", HTTP_REFERER="https://google.com")
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(r2["Location"], "https://example.com/docs")
        self.assertEqual(r2["X-Edge-Cache"], "HIT")

        # Verify Click Analytics recorded both clicks
        analytics_resp = self.client.get(f"/analytics/{key}")
        self.assertEqual(analytics_resp.status_code, 200)
        stats = analytics_resp.json()
        self.assertEqual(stats["key"], key)
        self.assertEqual(stats["total_clicks"], 2)
        self.assertEqual(len(stats["top_referers"]), 2)

    def test_hot_links_cache_miss_populates_from_link_store(self):
        resp = self.client.post(
            "/shorten",
            data=json.dumps({"url": "https://example.com/hot"}),
            content_type="application/json",
        )
        key = resp.json()["key"]
        caches["default"].clear()
        caches["edge"].clear()

        r1 = self.client.get(f"/{key}")
        self.assertEqual(r1.status_code, 302)
        self.assertEqual(r1["X-Hot-Cache"], "MISS")

        caches["edge"].clear()
        r2 = self.client.get(f"/{key}")
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(r2["X-Hot-Cache"], "HIT")

    def test_invalid_url_rejected(self):
        resp = self.client.post(
            "/shorten",
            data=json.dumps({"url": "not-a-valid-url"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_expired_link_returns_410_and_cleanup_deletes_it(self):
        expired_time = timezone.now() - timedelta(seconds=10)
        Url.objects.create(uuid="exp123", link="https://example.com/old", expires_at=expired_time)

        r = self.client.get("/exp123")
        self.assertEqual(r.status_code, 410)

        deleted = run_expiry_cleanup()
        self.assertEqual(deleted, 1)
        self.assertFalse(Url.objects.filter(uuid="exp123").exists())

    def test_cleanup_endpoint_and_management_command(self):
        expired_time = timezone.now() - timedelta(seconds=5)
        Url.objects.create(uuid="cmd1", link="https://example.com/1", expires_at=expired_time)
        Url.objects.create(uuid="live1", link="https://example.com/2", expires_at=timezone.now() + timedelta(hours=1))

        resp = self.client.post("/internal/cleanup")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["deleted"], 1)
        self.assertTrue(Url.objects.filter(uuid="live1").exists())

        Url.objects.create(uuid="cmd2", link="https://example.com/3", expires_at=expired_time)
        call_command("cleanup_expired")
        self.assertFalse(Url.objects.filter(uuid="cmd2").exists())

    def test_not_found_returns_404(self):
        r = self.client.get("/doesnotexist")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(ClickEvent.objects.filter(key="doesnotexist").count(), 0)
