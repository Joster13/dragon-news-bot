"""Regressions from the 15 Oct 2026 15:01 Moscow digest.

A keyword must denote the actual topic, not occur inside another word.
"""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from direct_news import category, select_balanced
from news import NewsItem

NOW = datetime(2026, 10, 15, 15, 1, tzinfo=ZoneInfo("Europe/Moscow"))


def item(title, topic, description=""):
    return NewsItem(topic, title, description, "https://example.org/story", "Source", NOW)


class FalsePositiveBoundaryTests(unittest.TestCase):
    def test_power_banks_not_finances(self):
        title = "Эксперты рассказали, запретят ли в самолетах пауэрбанки после серии возгораний"
        self.assertIsNone(category(title, "Аккумуляторы используют в смартфонах"))

    def test_party_activists_contribution_not_bank_deposit(self):
        title = "Медведев отметил вклад первичных отделений ЕР в сбор предложений"
        self.assertIsNone(category(title, "Собрано множество предложений для программы партии"))

    def test_exemption_not_special_military_operation(self):
        title = "ГД одобрила в I чтении освобождение от госпошлины на недвижимость ГУПов и МУПов"
        self.assertEqual(category(title), "Законы и правила")

    def test_real_war_title_still_classified(self):
        self.assertEqual(category("Над Севастополем сбили три БПЛА"), "СВО — позиции сторон")

    def test_real_crypto_is_finance(self):
        self.assertEqual(category("В России запретят P2P-сделки с криптовалютой с июля 2027 года"),
                         "Финансы и крипта")

    def test_bank_calls_is_finance(self):
        self.assertEqual(category("Операторы связи согласились отложить блокировку звонков банков без маркировки"),
                         "Финансы и крипта")

    def test_paid_ai_marketing_roundup_excluded(self):
        self.assertIsNone(category("От Алисы AI до психологии рекламы: 5 статей октября",
                                   "Дайджест click.ru из пяти рекламных материалов"))

    def test_expert_predicted_strikes_not_major_war_news(self):
        self.assertIsNone(category("Эксперт в области БПЛА предрек жесткие удары по Украине благодаря обучению нейросетей"))

    def test_new_lipetsk_bpla_retained(self):
        self.assertEqual(category("Липецкая область в числе 14 регионов страны, над которыми перехвачены БПЛА",
                                  forced="Липецк и Липецкая область"),
                         "Липецк и Липецкая область")

    def test_no_repeat_rss_headline_only_as_news(self):
        # A missing text snippet cannot be presented as verified explanatory content.
        title = "Над Севастополем сбили три БПЛА"
        news = item(title, "СВО — позиции сторон")
        self.assertTrue(news.title)
        self.assertFalse(news.summary)

if __name__ == "__main__":
    unittest.main()
