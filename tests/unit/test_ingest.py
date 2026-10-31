import unittest

from shared.config.registry import RegistryError, load_registry, validate
from shared.security.url_guard import UrlRejected, check_url
from workers.ingest.normalise import canonical_url, parse_feed
from workers.intelligence.classify import classify
from workers.intelligence.dedup import similarity, tokens


def resolver_for(address):
    return lambda host, port, type=None: [(2, 1, 6, "", (address, port))]


class UrlGuardTests(unittest.TestCase):
    def test_blocks_private_and_metadata_addresses(self):
        for address in ("127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"):
            with self.assertRaises(UrlRejected, msg=address):
                check_url("https://example.test/feed", resolver=resolver_for(address))

    def test_blocks_literal_ips_schemes_and_userinfo(self):
        for url in ("http://127.0.0.1/", "ftp://example.test/", "https://user:pw@example.test/", "file:///etc/passwd"):
            with self.assertRaises(UrlRejected, msg=url):
                check_url(url, resolver=resolver_for("93.184.216.34"))

    def test_mixed_dns_answer_is_rejected(self):
        def mixed(host, port, type=None):
            return [(2, 1, 6, "", ("93.184.216.34", port)), (2, 1, 6, "", ("10.0.0.1", port))]
        with self.assertRaises(UrlRejected):
            check_url("https://example.test/", resolver=mixed)

    def test_public_address_is_pinned(self):
        checked = check_url("https://example.test/feed", resolver=resolver_for("93.184.216.34"))
        self.assertEqual(checked.ip, "93.184.216.34")


class FeedTests(unittest.TestCase):
    def test_parses_rss_and_strips_markup(self):
        xml = (b"<rss><channel><item><title>A &amp; B</title><link>https://x.test/a/?utm_source=z</link>"
               b"<description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description>"
               b"<pubDate>Fri, 30 Oct 2026 09:30:00 GMT</pubDate></item></channel></rss>")
        item = parse_feed(xml)[0]
        self.assertEqual(item.title, "A & B")
        self.assertEqual(item.url, "https://x.test/a")
        self.assertEqual(item.excerpt, "Hello world")
        self.assertEqual(item.published_at.year, 2026)

    def test_parses_atom(self):
        xml = (b"<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>Paper</title>"
               b"<link rel='alternate' href='https://arxiv.org/abs/1'/><author><name>Ada</name></author>"
               b"<summary>Abstract</summary><published>2026-10-29T17:59:29Z</published></entry></feed>")
        item = parse_feed(xml)[0]
        self.assertEqual((item.author, item.url), ("Ada", "https://arxiv.org/abs/1"))

    def test_rejects_entity_expansion(self):
        xml = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "x">]><rss><channel><item><title>&a;</title></item></channel></rss>'
        with self.assertRaises(Exception):
            parse_feed(xml)

    def test_extracts_only_https_images(self):
        xml = (b"<rss xmlns:media='http://search.yahoo.com/mrss/'><channel>"
               b"<item><title>A</title><link>https://x.test/a</link><media:content url='https://cdn.test/a.jpg' medium='image'/></item>"
               b"<item><title>B</title><link>https://x.test/b</link><description>&lt;img src='http://cdn.test/b.jpg'&gt;</description></item>"
               b"<item><title>C</title><link>https://x.test/c</link><description>&lt;img src='https://cdn.test/c.png'&gt;</description></item>"
               b"</channel></rss>")
        images = [item.image_url for item in parse_feed(xml)]
        self.assertEqual(images, ["https://cdn.test/a.jpg", None, "https://cdn.test/c.png"])

    def test_rejects_non_http_links(self):
        self.assertIsNone(canonical_url("javascript:alert(1)"))


class IntelligenceTests(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(classify("Humanoid robot learns to walk", "")[0], "Robotics")
        self.assertEqual(classify("EU lawmakers pass new AI regulation", "")[0], "Policy")
        self.assertEqual(classify("A thing happened", "")[0], "Industry")
        self.assertEqual(classify("Neural thickets", "We propose a method", "Research")[0], "Research")

    def test_title_similarity(self):
        a = tokens("OpenAI releases new reasoning model for developers")
        b = tokens("OpenAI releases a new reasoning model for developers today")
        c = tokens("Regulators open consultation on AI transparency")
        self.assertGreater(similarity(a, b), 0.6)
        self.assertLess(similarity(a, c), 0.2)


class RegistryTests(unittest.TestCase):
    def test_shipped_registry_is_valid_and_https_only(self):
        sources = load_registry()
        self.assertTrue(sources)
        self.assertTrue(all(source.url.startswith("https://") for source in sources))

    def test_rejects_incomplete_or_insecure_entries(self):
        base = dict(id="x", name="X", type="rss", url="https://x.test/f", owner="o", tier=1, status="active",
                    schedule_minutes=60, rate_limit_per_minute=6, allowed_paths=[], terms_checked_on="2026-10-31",
                    terms_reference="https://x.test", copyright_position="excerpts_and_links", contact="a@b.c")
        self.assertEqual(len(validate([base])), 1)
        for change in ({"url": "http://x.test/f"}, {"terms_checked_on": None}, {"type": "web"}, {"tier": 4}):
            with self.assertRaises(RegistryError, msg=str(change)):
                validate([{**base, **change}])
        with self.assertRaises(RegistryError):
            validate([base, base])


if __name__ == "__main__":
    unittest.main()
