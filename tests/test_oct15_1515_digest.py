"""Regressions reproduced from Dragon News /preview at 15:15 Moscow, 2026-10-15."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from direct_news import category, select_balanced
from editorial import same_event, editorial_score
from news import NewsItem

NOW = datetime(2026, 10, 15, 15, 15, tzinfo=ZoneInfo("Europe/Moscow"))


def article(title, topic="Законы и правила", description="", source="ТАСС"):
    return NewsItem(topic, title, description,
                    "https://example.org/article/" + source.lower(),
                    source, NOW)


class October15Regressions(unittest.TestCase):
    def test_two_fish_breeding_bills_are_same_vote(self):
        item1 = article(
            "Законопроект о селекции и воспроизводстве рыбы принят в I чтении",
            description=("Госдума приняла в первом чтении законопроект № 1276697-8, "
                         "который позволит Росрыболовству воспроизводить объекты "
                         "аквакультуры за счет государственного задания."),
            source="Интерфакс"
        )
        item2 = article(
            "ГД приняла в I чтении законопроект о разведении лососевых за счет средств госзадания",
            description="Поддержка российских форелеводов качественным посадочным материалом.",
            source="ТАСС"
        )
        self.assertTrue(same_event(item1, item2))
        self.assertEqual(len(select_balanced([item1, item2], 30, set())), 1)

    def test_different_fisheries_bill_numbers_remain_separate(self):
        first = article(
            "ГД приняла в I чтении законопроект о разведении лососевых за счет средств госзадания",
            description="Законопроект № 1276697-8"
        )
        second = article(
            "ГД приняла в I чтении законопроект о воспроизводстве рыбы за счет госзадания",
            description="Законопроект № 9876543-2"
        )
        self.assertFalse(same_event(first, second))

    def test_veteran_tax_benefit_not_combat(self):
        title = "В Кировской области налоговую льготу для бойцов СВО распространили на жен и вдов"
        self.assertEqual(category(title), "Законы и правила")
        entry = article(title)
        self.assertNotIn(entry, select_balanced([entry], 30, set()))

    def test_starshield_ukraine_coverage_from_description(self):
        title = "Маск: Ограничения скорости Starshield устанавливают военные США и президент, а не SpaceX"
        summary = "Терминалы Starshield использует Украина для военных задач."
        self.assertEqual(category(title, summary), "СВО — позиции сторон")

    def test_books_story_not_major_world_news(self):
        self.assertIsNone(category("Салли Руни прекращает поставки книг в Британию из-за запрета Palestine Action"))

    def test_promotional_ai_digest_is_filtered(self):
        self.assertIsNone(category("От Алисы AI до психологии рекламы: 5 статей октября"))

    def test_actor_ai_opinion_is_filtered(self):
        self.assertIsNone(category("Ямпольская выступила против «воскрешения» умерших актеров с помощью ИИ"))

    def test_data_centers_in_mines_idea_is_filtered(self):
        self.assertIsNone(category("В России предложили возводить дата-центры в карьерах"))

    def test_retro_game_rerelease_is_filtered(self):
        self.assertIsNone(category("В Steam вышел классический квест-симулятор бильярда «Провинциальный игрок», который «Акелла» издала в 1999 году"))

    def test_apple_intelligence_is_it(self):
        self.assertEqual(category("В КНР запустят бета-версию платформы Apple Intelligence"), "IT, облака и AI")

    def test_real_ai_infrastructure_still_survives(self):
        title = "Рабочая группа по ИИ предложила смягчить ограничения для облачных сервисов в КИИ из-за белых списков"
        self.assertEqual(category(title), "IT, облака и AI")

    def test_ukraine_weapons_news_still_war(self):
        self.assertEqual(category("Великобритания ускорит поставку вооружений для Украины"), "СВО — позиции сторон")


if __name__ == "__main__":
    unittest.main()
