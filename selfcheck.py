"""Fast offline diagnostics for the *running* Dragon News process.

No HTTP requests and no secrets are read. This command tells the owner whether
BotHost has actually started a build containing the latest editorial rules.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from direct_news import category, select_balanced
from editorial import same_event
from editorial_gate import is_publishable
from news import NewsItem

BUILD_ID = "2026.10.15-editorial-audit-4"


def run_selfcheck() -> str:
    now = datetime.now(ZoneInfo("Europe/Moscow"))
    results: list[tuple[str, bool, str]] = []

    def test(name: str, fn):
        try:
            ok = bool(fn())
            results.append((name, ok, "" if ok else "неверный результат"))
        except Exception as err:
            results.append((name, False, type(err).__name__))

    def article(title: str, summary: str, source: str) -> NewsItem:
        return NewsItem(
            "Законы и правила", title, summary,
            "https://example.org/news/" + source.lower(),
            source, now,
        )

    fish1 = article(
        "Законопроект о селекции и воспроизводстве рыбы принят в I чтении",
        "Госдума приняла в первом чтении законопроект № 1276697-8, который "
        "позволит федеральным учреждениям разводить рыбу за счёт государственного задания.",
        "Интерфакс",
    )
    fish2 = article(
        "ГД приняла в I чтении законопроект о разведении лососевых за счет средств госзадания",
        "Это обеспечит поставки материала российским форелеводам.",
        "ТАСС",
    )

    test("Закон о рыбе: одно событие", lambda:
         same_event(fish1, fish2) and
         len(select_balanced([fish1, fish2], 28, set())) == 1)
    test("Криминал не кибербезопасность", lambda:
         category("Пытавшие подростков на автомойке вымогатели предстали перед судом") is None)
    test("Идея ЦОД в карьерах исключена", lambda:
         category("В России предложили возводить дата-центры в карьерах") is None)
    test("Мнение об актёрах и ИИ исключено", lambda:
         category("Ямпольская выступила против «воскрешения» умерших актеров с помощью ИИ") is None)
    test("Игра 1999 года исключена", lambda:
         category("В Steam вышел классический квест-симулятор бильярда "
                  "«Провинциальный игрок», который «Акелла» издала в 1999 году") is None)
    test("Рекомендации о финансовой подушке исключены", lambda:
         category("Названы три главных правила формирования финансовой подушки") is None)
    test("Справка о кешбэке исключена", lambda:
         category("Россиянам рассказали о праве банка аннулировать начисленный кешбэк") is None)
    test("Областные предупреждения сохраняются", lambda:
         category("Липецкая область в числе 14 регионов, над которыми перехвачены БПЛА",
                  forced="Липецк и Липецкая область") == "Липецк и Липецкая область")
    test("P2P классифицирован как финансы", lambda:
         category("В России запретят P2P-сделки с криптовалютой с июля 2027 года") == "Финансы и крипта")
    test("CVE классифицирован как кибербезопасность", lambda:
         category("Критическая уязвимость CVE-2026-12345 обнаружена в серверном ПО") == "Инфраструктура и безопасность")

    def gate_item(topic: str, title: str) -> NewsItem:
        return NewsItem(
            topic, title,
            "Свежая публикация с достаточным описанием для проверки тематической значимости.",
            "https://example.org/item", "Test source", now,
        )

    test("ИИ-метки YouTube Music не VPN", lambda: not is_publishable(gate_item(
        "Интернет и VPN", "YouTube Music начал внедрять ИИ-метки для музыкального контента")))
    test("Экстрадиция не финансовая новость", lambda: not is_publishable(gate_item(
        "Финансы и крипта", "В РФ экстрадировали совершившего незаконные валютные операции на 2,7 млрд рублей")))
    test("OpenAI-криминал не IT-релиз", lambda: not is_publishable(gate_item(
        "IT, облака и AI", "Туалетная бумага и прослушивающее устройство. Что известно об аресте инженера OpenAI?")))
    test("Мнение об экономике ИИ не релиз", lambda: not is_publishable(gate_item(
        "IT, облака и AI", "ВЭБ.РФ: Внедрение ИИ выведет экономику РФ на новый уровень роста")))
    test("Идея ЦОД без строительства исключена", lambda: not is_publishable(gate_item(
        "Инфраструктура и безопасность", "Правительство заинтересовалось переносом дата-центров в угольные регионы России")))
    test("Microsoft Maia остаётся", lambda: is_publishable(gate_item(
        "IT, облака и AI", "Microsoft представила XPU-ускоритель Maia 300 для инференса ИИ")))
    test("Настоящий VPN-запрет остаётся", lambda: is_publishable(gate_item(
        "Интернет и VPN", "Роскомнадзор ограничил работу VPN и мобильного интернета")))
    test("Новости о критических CVE остаются", lambda: is_publishable(gate_item(
        "Инфраструктура и безопасность", "Критическая уязвимость CVE-2026-12345 обнаружена в серверном ПО")))

    sample_description = (
        "Публикация содержит подтверждённые детали изменений, сроки, "
        "условия и факты, которые непосредственно затрагивают банковские операции."
    )
    finance_titles = [
        "ЦБ снизил ключевую ставку по решению совета директоров",
        "Банк увеличил проценты по вкладам для клиентов",
        "В России запретили P2P-переводы без идентификации клиента",
        "Банки ограничили снятие наличных с новых счетов",
    ]
    finance_examples = [
        NewsItem("Финансы и крипта", title, sample_description,
                 "https://example.org/" + str(i), "Интерфакс", now)
        for i, title in enumerate(finance_titles)
    ]
    test("Больше двух важных новостей одного СМИ", lambda:
         len(select_balanced(finance_examples, 28, set())) == 4)
    sparse = finance_examples[:2] + [
        NewsItem(item.topic, item.title, "", item.link, item.source, item.published)
        for item in finance_examples[2:]
    ]
    test("Без описания не заполнять объём", lambda:
         len(select_balanced(sparse, 28, set())) == 2)

    passed = sum(ok for _, ok, _ in results)
    lines = [
        "DRAGON NEWS · проверка сборки",
        f"Версия: {BUILD_ID}",
        f"Редакционные проверки: {passed}/{len(results)}",
    ]
    for name, ok, reason in results:
        lines.append(f"{'✓' if ok else '✗'} {name}" + (f" ({reason})" if reason else ""))
    lines.append("Тесты выполняются в запущенном процессе BotHost, без загрузки новостей.")
    return "\n".join(lines)
