"""Smoke tests for currently supported direct-news pipeline."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from news import NewsItem
from direct_news import category, has_details, Feed, rss_items
from rendering import rich_html

NOW = datetime(2026, 10, 15, 9, tzinfo=ZoneInfo("Europe/Moscow"))


class NewsQualityTests(unittest.TestCase):
    def test_no_duplicate_headline_as_description(self):
        self.assertFalse(has_details("В Липецке отключат воду", "В Липецке отключат воду"))
        self.assertTrue(has_details("В Липецке отключат воду", "Отключение затронет несколько адресов из-за ремонта трубопровода."))

    def test_direct_rss_retains_original_link(self):
        xml = (
            '<rss><channel><item><title>'
            'В Липецке отключат холодную воду'
            '</title><link>https://example.com/news/123</link>'
            '<pubDate>Thu, 15 Oct 2026 08:00:00 +0300</pubDate><description>'
            'Из-за ремонта водопровода отключение затронет несколько улиц Липецка.'
            '</description></item></channel></rss>'
        ).encode("utf-8")
        data = rss_items(Feed("Publisher", "https://example.com/rss"), xml, NOW)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].link, "https://example.com/news/123")

    def test_substantive_vpn_news(self):
        self.assertEqual(category("РКН ограничил работу VPN"), "Интернет и VPN")

    def test_no_rss_footer(self):
        self.assertNotIn("Автоматический обзор по публичным лентам", rich_html([], NOW))

    def test_no_ads_from_games(self):
        self.assertIsNone(category("Скидки на компьютерные игры: топ-10 предложений"))

if __name__ == "__main__":
    unittest.main()
