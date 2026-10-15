"""Source-diversity and second-pass recovery for high-quality news."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from news import NewsItem
from direct_news import select_balanced

NOW = datetime(2026, 10, 15, 17, tzinfo=ZoneInfo("Europe/Moscow"))
DETAILS = ("Подтверждены новые сроки и конкретные условия изменения. "
           "Публикация содержит сведения, которые могут повлиять на финансовые "
           "решения пользователей, размеры платежей и действия организаций.")


def news(title, source="Интерфакс", topic="Финансы и крипта", description=DETAILS):
    return NewsItem(topic, title, description, "https://example.org/" + str(len(title)), source, NOW)


class HigherCoverageTests(unittest.TestCase):
    def test_adds_more_than_two_significant_stories_from_one_source(self):
        posts = [
            news("ЦБ снизил ключевую ставку по решению совета директоров"),
            news("Банк увеличил проценты по вкладам для клиентов"),
            news("В России запретили P2P-переводы без идентификации клиента"),
            news("Банки ограничили снятие наличных с новых счетов"),
        ]
        selected = select_balanced(posts, 28, set())
        self.assertEqual(len(selected), 4)
        self.assertEqual(len({p.title for p in selected}), 4)

    def test_headline_only_stories_do_not_fill_source_quota(self):
        posts = [
            news("ЦБ снизил ключевую ставку по решению совета директоров"),
            news("Банк увеличил проценты по вкладам для клиентов"),
            news("В России запретили P2P-переводы без идентификации клиента", description=""),
            news("Банки ограничили снятие наличных с новых счетов", description=""),
        ]
        selected = select_balanced(posts, 28, set())
        self.assertEqual(len(selected), 2)

    def test_preserves_inclusion_filter_when_more_is_available(self):
        posts = [
            news("ЦБ снизил ключевую ставку по решению совета директоров"),
            news("Банк увеличил проценты по вкладам для клиентов"),
            news("Названы три главных правила формирования финансовой подушки"),
            news("Экстрадировали подозреваемого по делу о незаконных валютных операциях"),
        ]
        titles = [p.title for p in select_balanced(posts, 28, set())]
        self.assertEqual(len(titles), 2)
        self.assertFalse(any("подушки" in x or "Экстрадировали" in x for x in titles))

    def test_max_items_is_respected(self):
        posts = [
            news("ЦБ снизил ключевую ставку по решению совета директоров"),
            news("Банк увеличил проценты по вкладам для клиентов"),
            news("В России запретили P2P-переводы без идентификации клиента"),
            news("Банки ограничили снятие наличных с новых счетов"),
        ]
        self.assertEqual(len(select_balanced(posts, 3, set())), 3)

    def test_no_unrelated_news_added_to_hit_target(self):
        posts = [news("ЦБ снизил ключевую ставку по решению совета директоров")]
        self.assertEqual(len(select_balanced(posts, 28, set())), 1)


if __name__ == "__main__":
    unittest.main()
