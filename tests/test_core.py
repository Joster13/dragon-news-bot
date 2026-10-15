import sys
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from news import NewsItem, clean_snippet, decode_feed, news_rss_url
from rendering import rich_html, fallback_html

MOSCOW = ZoneInfo('Europe/Moscow')

class CoreTests(unittest.TestCase):
    def test_rss_parsing_strict_time(self):
        now = datetime(2026, 10, 15, 9, 0, tzinfo=MOSCOW)
        rss = b'''<rss version="2.0"><channel><item><title>Today news - SourceA</title>
        <link>https://example.org/story</link><pubDate>Thu, 15 Oct 2026 05:00:00 GMT</pubDate>
        <description>Important changes</description></item>
        <item><title>Old news - SourceB</title><link>https://example.org/old</link>
        <pubDate>Mon, 12 Oct 2026 05:00:00 GMT</pubDate></item>
        <item><title>Unknown date</title><link>https://example.org/undated</link></item>
        </channel></rss>'''
        out = decode_feed('Россия — главное', '', rss, now)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].published.hour, 8)
        self.assertEqual(out[0].source, 'SourceA')

    def test_rich_escaped_and_details(self):
        now = datetime(2026, 10, 15, 9, tzinfo=MOSCOW)
        item = NewsItem('Липецк и Липецкая область', 'New <script> & event', 'Some <unsafe> & literal',
                        'https://example.org?a=1&b=2', 'Источник', now)
        raw = rich_html([item], now)
        self.assertIn('<details open>', raw)
        self.assertIn('New &lt;script&gt;', raw)
        self.assertNotIn('<unsafe>', raw)
        self.assertIn('a=1&amp;b=2', raw)
        fallback = fallback_html([item], now)
        self.assertTrue(fallback)
        self.assertNotIn('<script>', ''.join(fallback))

    def test_rss_query(self):
        self.assertIn('news.google.com', news_rss_url('Липецк when:1d'))

if __name__ == '__main__':
    unittest.main()
