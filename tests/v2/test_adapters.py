"""Offline fixtures for HTTPS registry and public feed adapters."""
import unittest
from datetime import datetime, timezone
from dragon_news_v2.adapters import parse_feed, validated_source_url
from dragon_news_v2.source_registry import SourceSpec, load_source_specs

NOW = datetime(2026,10,15,10,tzinfo=timezone.utc)
RSS = b'''<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Important RSS update</title><link>https://example.org/story?utm_source=rss&amp;id=42</link>
<description><![CDATA[<p>New <b>facts</b> and details.</p>]]></description>
<pubDate>Thu, 15 Oct 2026 09:35:00 +0300</pubDate></item>
<item><title>Missing timestamp</title><link>https://example.org/missing</link>
<description>No date supplied.</description></item>
<item><title>Duplicate tracked URL</title><link>https://example.org/story?id=42&amp;utm_medium=mail</link>
<pubDate>Thu, 15 Oct 2026 09:35:00 +0300</pubDate></item>
</channel></rss>'''
ATOM = '''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<title>Atom title</title><id>guid123</id><updated>2026-10-15T10:00:00+03:00</updated>
<link rel="alternate" href="https://example.org/atom" /><summary>Atom details</summary>
</entry></feed>'''.encode()
TELEGRAM = '''<div class="tgme_widget_message" data-post="example_channel/123">
 <div class="tgme_widget_message_text">New regional public alert. Detailed information here.</div>
 <time datetime="2026-10-15T08:14:00+00:00"></time></div>'''.encode()


def spec(kind="rss", max_bytes=10000):
    return SourceSpec("test", "https://example.org/feed", kind, ("Россия — главное",), max_bytes, 3600)


class SourceAdapterTests(unittest.TestCase):
    def test_timezone_and_missing_timestamp(self):
        items = parse_feed(spec(),RSS,NOW)
        self.assertEqual(len(items),3)
        self.assertEqual(items[0].published_at, datetime(2026,10,15,6,35,tzinfo=timezone.utc))
        self.assertIsNone(items[1].published_at)
        self.assertIsNone(items[0].event_time)

    def test_tracking_url_canonicalization(self):
        items = parse_feed(spec(),RSS,NOW)
        self.assertEqual(items[0].canonical_url, "https://example.org/story?id=42")
        self.assertEqual(items[0].canonical_url, items[2].canonical_url)
        self.assertEqual(items[0].article_id, items[2].article_id)

    def test_html_markup_and_encoding(self):
        items = parse_feed(spec(),RSS,NOW)
        self.assertEqual(items[0].excerpt, "New facts and details.")
        self.assertEqual(parse_feed(spec("atom"),ATOM,NOW)[0].title,"Atom title")

    def test_private_redirect_rejected(self):
        allowed=frozenset({"example.org"})
        for url in ["http://example.org/path","https://127.0.0.1/", "https://example.org@127.0.0.1/", "https://localhost/", "https://example.org:8080/x", "https://evil.org/x", "https://example.org\\@evil.org/x"]:
            with self.subTest(url=url):
                self.assertIsNone(validated_source_url(url,allowed))
        self.assertEqual(validated_source_url("https://example.org/valid",allowed),"https://example.org/valid")

    def test_article_size_cap(self):
        with self.assertRaises(ValueError):
            parse_feed(spec(max_bytes=100),RSS,NOW)

    def test_public_telegram_time_parsing(self):
        items=parse_feed(spec("public_telegram"),TELEGRAM,NOW)
        self.assertEqual(len(items),1)
        self.assertEqual(items[0].canonical_url,"https://t.me/example_channel/123")
        self.assertEqual(items[0].published_at,datetime(2026,10,15,8,14,tzinfo=timezone.utc))

    def test_registry_stable_and_only_public_https(self):
        specs=load_source_specs()
        self.assertTrue(len(specs)>=10)
        self.assertEqual(len(specs),len({s.source_id for s in specs}))
        self.assertTrue(all(s.url.startswith("https://") for s in specs))


if __name__=='__main__': unittest.main()
