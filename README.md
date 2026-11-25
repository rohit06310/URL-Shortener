# URL Shortener

A modular Django URL shortener implementing a distributed system design with edge caching, round-robin load balancing, range-based Base62 key generation, hot-link caching, TTL expiry cleanup, and async click analytics.

## Architecture Overview

| Component | Implementation | Location |
|---|---|---|
| **Edge Cache (CDN)** | Middleware caching `GET /{key}` redirects (`X-Edge-Cache: HIT \| MISS`) | [`shortener/middleware.py`](shortener/middleware.py) |
| **Load Balancer** | Round-robin node routing (`X-Served-By: shortener-node-1..3`) | [`shortener/middleware.py`](shortener/middleware.py) |
| **Shortener Service** | Validates URLs, orchestrates key generation, storage, and caching | [`shortener/services/shortener.py`](shortener/services/shortener.py) |
| **Range Allocator** | Atomically claims non-overlapping ID ranges (`KeyRange`) | [`shortener/services/range_allocator.py`](shortener/services/range_allocator.py) |
| **Key Generation Service** | Thread-safe Base62 key dispenser backed by `RangeAllocator` | [`shortener/services/keygen.py`](shortener/services/keygen.py) |
| **Link Store** | Persistent URL mappings with optional `expires_at` TTL (`Url`) | [`shortener/services/link_store.py`](shortener/services/link_store.py) |
| **Hot Links Cache** | In-memory cache (`LocMemCache` by default, or Redis via `REDIS_URL`) | [`shortener/services/cache.py`](shortener/services/cache.py) |
| **Expiry Cleanup** | Deletes expired links and evicts stale cache entries | [`shortener/services/cleanup.py`](shortener/services/cleanup.py) |
| **Click Events** | Non-blocking background queue (`queue.Queue`) for redirect events | [`shortener/services/events.py`](shortener/services/events.py) |
| **Click Analytics** | Aggregated click counts, daily breakdown, and top referers | [`shortener/services/analytics.py`](shortener/services/analytics.py) |

## Quick Start (Local)

### 1. Run with `uv` (Recommended, Python 3.12+)

```bash
uv run --with django python manage.py migrate
uv run --with django python manage.py runserver 127.0.0.1:8000
```

### 2. Or Run with Virtual Environment (Python 3.12)

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/` in your browser.

### Optional: Use Redis for Hot Links & Edge Caches

By default, the app uses Django's `LocMemCache` so it runs with zero external services. To use Redis:

```bash
export REDIS_URL=redis://127.0.0.1:6379/1
```

## API & Endpoints

### Shorten a URL
```bash
curl -X POST http://127.0.0.1:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "ttl_seconds": 3600}'
```
Response (`201 Created`):
```json
{
  "key": "q0U",
  "short_url": "http://127.0.0.1:8000/q0U",
  "link": "https://example.com",
  "expires_at": "2026-11-25T02:00:00+00:00"
}
```

### Redirect
```bash
curl -i http://127.0.0.1:8000/q0U
```
Returns `302 Found` (or `410 Gone` if expired, `404 Not Found` if missing), along with `X-Edge-Cache` and `X-Served-By` headers.

### View Click Analytics
```bash
curl http://127.0.0.1:8000/analytics/q0U
```

### Run Expiry Cleanup
```bash
# Via management command
uv run --with django python manage.py cleanup_expired

# Or via internal endpoint
curl -X POST http://127.0.0.1:8000/internal/cleanup
```

## Running Tests

```bash
uv run --with django python manage.py test
```
