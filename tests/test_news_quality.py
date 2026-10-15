import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from news import NewsItem, is_significant
from article_content import description_from_html, short_extract, safe_public_url
from rendering import rich_html

NOW = datetime(2026, 10, 15, 9, tzinfo=ZoneInfo("Europe/Moscow"))


def item(topic, title):
    return NewsItem(topic, title, "", "https://example.com/story", "Example", NOW)


class NewsQualityTests(unittest.TestCase):
    def test_unrelated_truck_not_in_vpn(self):
        self.assertFalse(is_significant(item("Интернет и VPN", "Троих задержали после преследования и блокировки грузовика в Туркестанской области")))

    def test_real_vpn_headline(self):
        self.assertTrue(is_significant(item("Интернет и VPN", "РКН ограничил доступ к VPN-протоколу в России")))

    def test_local_entertainment_dropped(self):
        self.assertFalse(is_significant(item("Липецк и Липецкая область", "Фестиваль «Липецкие театральные встречи» завершит спектакль")))

    def test_local_infrastructure_retained(self):
        self.assertTrue(is_significant(item("Липецк и Липецкая область", "В Липецкой области заменят 175 лифтов")))

    def test_meta_extract(self):
        markup = '<html><head><meta property="og:description" content="' + ("Стали известны подробности ремонта городской инфраструктуры. " * 3) + '"></head></html>'
        self.assertGreater(len(description_from_html(markup)), 100)

    def test_article_body_extract(self):
        markup = '<html><article><p>' + ("Департамент сообщил о плановом ремонте инженерных коммуникаций. " * 4) + '</p></article></html>'
        self.assertGreater(len(description_from_html(markup)), 150)

    def test_short_extract_limited(self):
        long = ("Официальный представитель рассказал о работах в регионе. " * 40)
        self.assertLessEqual(len(short_extract(long).split()), 41)

    def test_private_hosts_rejected(self):
        self.assertFalse(safe_public_url("https://127.0.0.1/test"))
        self.assertFalse(safe_public_url("http://example.org/story"))
        self.assertTrue(safe_public_url("https://example.org/story"))

    def test_no_footer(self):
        self.assertNotIn("Автоматический обзор по публичным лентам", rich_html([], NOW))


if __name__ == "__main__":
    unittest.main()
