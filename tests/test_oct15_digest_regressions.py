"""October 15, 2026 digest editorial regressions from Telegram output."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from news import NewsItem
from direct_news import category, select_balanced
from editorial import editorial_score

NOW = datetime(2026, 10, 15, 14, 41, tzinfo=ZoneInfo("Europe/Moscow"))


def article(title, topic="Законы и правила", source="ТАСС", desc=""):
    return NewsItem(topic, title, desc,
                    "https://example.org/story/" + str(abs(hash(title))),
                    source, NOW)


class RealDigestRegressions(unittest.TestCase):
    def test_party_election_quote_is_not_a_law(self):
        title = 'Медведев назвал победу "Единой России" на выборах в Госдуму исторической'
        self.assertIsNone(category(title))

    def test_generic_tax_tips_are_not_new_economic_policy(self):
        self.assertIsNone(category("Россиянам назвали легальные способы сэкономить на налогах"))

    def test_generic_economy_opinion_is_not_news(self):
        self.assertIsNone(category("В ТПП назвали основные точки роста российской экономики"))

    def test_parliament_opinion_is_not_legislation(self):
        self.assertIsNone(category("В Госдуме прокомментировали идею ввести предоплату для абитуриентов"))

    def test_parliament_actual_first_reading_is_law(self):
        self.assertEqual(
            category("Госдума одобрила проект о правовом статусе системы-112"),
            "Законы и правила",
        )

    def test_reading_of_property_swap_income_tax_bill(self):
        self.assertEqual(
            category("Госдума приняла в I чтении законопроект о расчете НДФЛ при обмене недвижимости"),
            "Законы и правила",
        )

    def test_generic_eu_mp_opinion_dropped(self):
        self.assertIsNone(category("В Европарламенте высказались об угрозе со стороны России"))

    def test_regulatory_crypto_news_still_retained(self):
        headline = "В России запретят P2P-сделки с криптовалютой с июля 2027 года"
        item = article(headline, "Финансы и крипта", "Хабр")
        self.assertEqual(category(headline), "Финансы и крипта")
        self.assertIn(item, select_balanced([item], 25, set()))

    def test_single_outlet_cannot_fill_legal_section(self):
        posts = [
            article("Госдума одобрила в первом чтении законопроект о системе-112",
                    source="ТАСС"),
            article("Госдума приняла законопроект о расчете НДФЛ при мене недвижимости",
                    source="ТАСС"),
            article("Госдума утвердила законопроект об управлении многоквартирными домами",
                    source="ТАСС"),
            article("Правительство утвердило законопроект о порядке регистрации бизнеса",
                    source="Интерфакс"),
        ]
        selected = select_balanced(posts, 25, set())
        self.assertLessEqual(sum(x.source == "ТАСС" for x in selected), 2)
        self.assertTrue(any(x.source == "Интерфакс" for x in selected))

    def test_small_number_of_important_items_not_padded(self):
        item = article("Госдума приняла законопроект о расчете НДФЛ при обмене недвижимости")
        self.assertEqual(len(select_balanced([item], 30, set())), 1)


if __name__ == "__main__":
    unittest.main()
