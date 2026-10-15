"""Regression tests for duplicate events and editorial relevance."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from news import NewsItem
from editorial import same_event, deduplicate, editorial_score
from direct_news import select_balanced

NOW = datetime(2026, 10, 15, 14, tzinfo=ZoneInfo("Europe/Moscow"))


def article(title, source="ТАСС", topic="Законы и правила", description=""):
    return NewsItem(topic, title, description,
                    "https://example.org/news/" + source.lower(), source, NOW)


class EventDedupTests(unittest.TestCase):
    def test_system112_two_publishers_same_event(self):
        tass = article("ГД приняла в I чтении законопроект о правовом статусе централизованной системы-112", "ТАСС")
        ria = article("Госдума одобрила проект о правовом статусе системы-112", "РИА Новости")
        self.assertTrue(same_event(tass, ria))
        self.assertEqual(len(deduplicate([tass, ria])), 1)
        self.assertEqual(len(select_balanced([tass, ria], 28, set())), 1)

    def test_different_readings_are_distinct_events(self):
        first = article("Госдума приняла в I чтении законопроект о статусе системы-112")
        second = article("Госдума приняла во II чтении законопроект о статусе системы-112")
        self.assertFalse(same_event(first, second))

    def test_different_tax_bills_remain_separate(self):
        one = article("Госдума приняла законопроект о расчёте НДФЛ при обмене недвижимости")
        two = article("Госдума одобрила законопроект о повышении НДС для предпринимателей")
        self.assertFalse(same_event(one, two))

    def test_different_numbers_remain_separate(self):
        a = article("Госдума одобрила законопроект о системе-112")
        b = article("Госдума одобрила законопроект о системе-122")
        self.assertFalse(same_event(a, b))

    def test_different_topics_not_merged(self):
        a = article("Судебное решение о блокировке сайта", topic="Интернет и VPN")
        b = article("Судебное решение о блокировке сайта", topic="Законы и правила")
        self.assertFalse(same_event(a, b))

    def test_positive_negative_action_not_merged(self):
        a = article("Парламент принял поправки о маркировке банковских звонков")
        b = article("Парламент отклонил поправки о маркировке банковских звонков")
        self.assertFalse(same_event(a, b))

    def test_removes_low_value_press_statement(self):
        a = article("В Кремле решили умолчать о желающих купить российское дизтопливо странах",
                    topic="Россия — главное")
        self.assertLess(editorial_score(a), 2)
        self.assertEqual(select_balanced([a], 28, set()), [])

    def test_high_impact_crypto_news_survives(self):
        a = article("В России запретят P2P-сделки с криптовалютой с 1 июля 2027 года",
                    topic="Финансы и крипта")
        self.assertEqual(select_balanced([a], 28, set()), [a])

    def test_other_publisher_reprint_next_day_removed(self):
        from types import SimpleNamespace
        original = SimpleNamespace(
            topic="Законы и правила",
            title="ГД приняла в I чтении законопроект о правовом статусе централизованной системы-112")
        reprint = article("Госдума одобрила проект о правовом статусе системы-112", "РИА Новости")
        self.assertEqual(select_balanced([reprint], 28, set(), recent_events=[original]), [])

    def test_storage_event_history(self):
        import tempfile
        from pathlib import Path
        from storage import Storage
        with tempfile.TemporaryDirectory() as tmp:
            db = Storage(str(Path(tmp) / "news.sqlite3"))
            item = article("Госдума одобрила законопроект о статусе системы-112")
            db.record("2026-10-15", "digest", [item.key], articles=[item])
            recent = db.recent_events()
            self.assertEqual(len(recent), 1)
            self.assertEqual(recent[0].title, item.title)
            db.conn.close()

    def test_previously_seen_item_not_emitted(self):
        a = article("Госдума приняла законопроект о расчете НДФЛ при обмене недвижимости")
        self.assertEqual(select_balanced([a], 28, {a.key}), [])

if __name__ == "__main__":
    unittest.main()
