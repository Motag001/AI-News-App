import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

_TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = os.path.join(_TEMP.name, "test.db")
os.environ["INGEST_ENABLED"] = "false"
os.environ["ALLOWED_HOSTS"] = "testserver,localhost"

import httpx  # noqa: E402

from api.main import app  # noqa: E402
from api.store import connection, initialise_database  # noqa: E402
from shared.config.registry import Source  # noqa: E402
from workers.ingest import run as ingest  # noqa: E402
from workers.ingest.http import FetchError, Response  # noqa: E402


def feed(entries):
    items = "".join(
        f"<item><title>{t}</title><link>{u}</link><description>{d}</description>"
        f"<pubDate>{p}</pubDate></item>" for t, u, d, p in entries
    )
    return f"<?xml version='1.0'?><rss version='2.0'><channel>{items}</channel></rss>".encode()


def rfc822(hours_ago):
    moment = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return moment.strftime("%a, %d %b %Y %H:%M:%S +0000")


SOURCE_A = Source("lab-a", "Lab A", "rss", "https://example.test/a.xml", "owner", 1, "active", 60, 6,
                  attribution="Courtesy of Lab A")
SOURCE_B = Source("press-b", "Press B", "rss", "https://example.test/b.xml", "owner", 2, "active", 60, 6)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialise_database()
        ingest.DOMAIN_GAP_SECONDS = 0
        with connection() as database:
            ingest.sync_sources(database, [SOURCE_A, SOURCE_B])
        a = feed([
            ("Robot arm learns warehouse picking", "https://example.test/robots?utm_source=x",
             "<p>A new robot system.</p>", rfc822(2)),
            ("Old story from last year", "https://example.test/old", "Old.", "Mon, 01 Jan 2024 00:00:00 +0000"),
        ])
        b = feed([
            ("Robot arm learns warehouse picking!", "https://press.test/robot-arm",
             "Coverage of the robot arm.", rfc822(1)),
            ("Regulators propose new AI law", "https://press.test/law", "Lawmakers publish a draft.", rfc822(3)),
        ])
        for source, body in ((SOURCE_A, a), (SOURCE_B, b)):
            ingest.ingest_source(source, fetch=lambda *args, body=body: Response(200, body, None, None))
        with connection() as database:
            ingest.rescore(database, datetime.now(timezone.utc))

    def get(self, path, params=None):
        async def send_request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.get(path, params=params)

        return asyncio.run(send_request())

    def test_health_and_categories(self):
        response = self.get("/api/v1/health")
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["sources"], 2)
        self.assertIn("content-security-policy", response.headers)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        categories = self.get("/api/v1/categories").json()
        self.assertTrue(any(category["name"] == "Robotics" for category in categories))

    def test_duplicates_are_grouped_and_old_items_skipped(self):
        stories = self.get("/api/v1/stories").json()
        titles = [story["title"] for story in stories["items"]]
        self.assertEqual(stories["total"], 2)
        self.assertNotIn("Old story from last year", titles)
        robot = next(story for story in stories["items"] if story["category"] == "Robotics")
        self.assertEqual(robot["source_count"], 2)
        details = self.get(f"/api/v1/stories/{robot['id']}").json()
        self.assertEqual(len(details["sources"]), 2)
        self.assertFalse(details["ai_generated"])
        self.assertIsNone(details["impact"])
        # Tracking parameters are stripped from stored links.
        self.assertIn("https://example.test/robots", [source["url"] for source in details["sources"]])
        self.assertEqual(details["sources"][0]["attribution"], "Courtesy of Lab A")

    def test_unknown_category_and_story_are_rejected(self):
        self.assertEqual(self.get("/api/v1/stories", {"category": "Other"}).status_code, 422)
        self.assertEqual(self.get("/api/v1/stories/not-valid!").status_code, 404)
        self.assertEqual(self.get("/api/v1/stories", {"limit": 51}).status_code, 422)

    def test_settings_page_is_served(self):
        response = self.get("/settings")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Content-Security-Policy", response.headers)

    def test_share_links_only_include_the_story_identifier(self):
        story_id = self.get("/api/v1/stories").json()["items"][0]["id"]
        result = self.get(f"/api/v1/stories/{story_id}/share-links").json()
        self.assertEqual(result["copy"], f"http://localhost:8000/story/{story_id}")

    def test_search_treats_wildcards_literally(self):
        self.assertEqual(self.get("/api/v1/stories", {"q": "%"}).json()["total"], 0)
        self.assertEqual(self.get("/api/v1/stories", {"q": "_"}).json()["total"], 0)
        self.assertEqual(self.get("/api/v1/stories", {"q": "warehouse"}).json()["total"], 1)

    def test_errors_use_problem_json(self):
        response = self.get("/api/v1/stories/not-valid!")
        self.assertEqual(response.headers["content-type"], "application/problem+json")
        invalid = self.get("/api/v1/stories", {"limit": 99})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.headers["content-type"], "application/problem+json")

    def test_expired_stories_and_items_are_deleted(self):
        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=31)).isoformat()
        with connection() as database:
            database.execute(
                "INSERT INTO story (id, canonical_title, category, credibility, importance, published_at, first_seen_at) "
                "VALUES ('s-expired', 'Expired', 'Industry', 0.5, 0.5, ?, ?)", (old, old))
            database.execute(
                "INSERT INTO item (source_id, story_id, title, canonical_url, fetched_at, title_hash) "
                "VALUES ('lab-a', 's-expired', 'Expired', 'https://example.test/expired', ?, 'h')", (old,))
            before = database.execute("SELECT COUNT(*) FROM story").fetchone()[0]
            self.assertEqual(ingest.purge_expired(database, now), 1)
            after = database.execute("SELECT COUNT(*) FROM story").fetchone()[0]
            leftover = database.execute("SELECT COUNT(*) FROM item WHERE story_id = 's-expired'").fetchone()[0]
        self.assertEqual((before - after, leftover), (1, 0))

    def test_unexpected_host_header_is_rejected(self):
        async def send_request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://evil.example") as client:
                return await client.get("/api/v1/health")

        self.assertEqual(asyncio.run(send_request()).status_code, 400)

    def test_security_headers_present(self):
        headers = self.get("/api/v1/health").headers
        for name in ("permissions-policy", "cross-origin-opener-policy", "x-frame-options", "referrer-policy"):
            self.assertIn(name, headers)
        self.assertIn("frame-ancestors 'none'", headers["content-security-policy"])
        self.assertNotIn("unsafe-inline", headers["content-security-policy"])

    def test_rate_limit_returns_429(self):
        import api.main as main
        original = main.RATE_LIMIT_PER_MINUTE
        main._recent_requests.clear()
        main.RATE_LIMIT_PER_MINUTE = 3
        try:
            codes = [self.get("/api/v1/health").status_code for _ in range(5)]
        finally:
            main.RATE_LIMIT_PER_MINUTE = original
            main._recent_requests.clear()
        self.assertEqual(codes, [200, 200, 200, 429, 429])

    def test_responses_are_cacheable_where_safe(self):
        self.assertIn("max-age", self.get("/api/v1/stories").headers["cache-control"])
        self.assertIn("max-age", self.get("/assets/app.css").headers["cache-control"])
        self.assertNotIn("cache-control", self.get("/api/v1/health").headers)

    def test_zz_failed_fetch_backs_off_and_keeps_stories(self):
        def broken(*_):
            raise FetchError("Network error: ConnectError.")

        self.assertEqual(ingest.ingest_source(SOURCE_A, fetch=broken), "failed")
        with connection() as database:
            row = database.execute("SELECT consecutive_failures FROM source WHERE id='lab-a'").fetchone()
        self.assertEqual(row["consecutive_failures"], 1)
        self.assertGreaterEqual(self.get("/api/v1/stories").json()["total"], 2)


if __name__ == "__main__":
    unittest.main()
