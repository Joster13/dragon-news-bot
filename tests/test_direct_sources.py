import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from direct_news import Feed, category, rss_items, telegram_items, select_balanced

NOW = datetime(2026, 10, 15, 14, 0, tzinfo=ZoneInfo("Europe/Moscow"))

class DirectSourcesTest(unittest.TestCase):
    def test_vpn_false_positive(self):
        self.assertIsNone(category("Полиция провела блокировку грузовика в Туркестане"))
    def test_vpn_actual(self):
        self.assertEqual(category("Роскомнадзор ограничил работу VPN в России"), "Интернет и VPN")
    def test_local_trivia(self):
        self.assertIsNone(category("Фестиваль театров в Липецке завершился"))
    def test_local_utilities(self):
        self.assertEqual(category("В Липецке отключат холодную воду"), "Липецк и Липецкая область")
    def test_rss_direct_item(self):
        data = b"""<rss><channel><item><title>В Липецке отключат холодную воду</title><link>https://example.org/article</link><pubDate>Thu, 15 Oct 2026 09:00:00 +0300</pubDate><description>В связи с ремонтными работами временно ограничено водоснабжение в нескольких домах города. Сроки уточняются у поставщика.</description></item></channel></rss>"""
        rows = rss_items(Feed("local","https://example.org/rss"), data, NOW)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].topic, "Липецк и Липецкая область")
        self.assertTrue(rows[0].link.endswith("/article"))
    def test_telegram_regional_posts(self):
        html = '<div class="tgme_widget_message" data-post="gorod48ru/999"><div class="tgme_widget_message_text">В Липецке отключат холодную воду. В связи с работами водоканала с утра без воды останется несколько улиц, о завершении работ сообщат дополнительно.</div><time datetime="2026-10-15T09:00:00+03:00"></time></div>'
        rows = telegram_items(Feed("GOROD48", "https://t.me/s/gorod48ru", "Липецк и Липецкая область"), html, NOW)
        self.assertEqual(len(rows),1)
        self.assertIn("Липецк", rows[0].topic)

if __name__ == "__main__":
    unittest.main()
