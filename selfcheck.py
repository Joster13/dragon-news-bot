"""Fast offline diagnostics for the *running* Dragon News process.

No HTTP requests and no secrets are read. This command tells the owner whether
BotHost has actually started a build containing the latest editorial rules.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from direct_news import category, select_balanced
from editorial import same_event
from news import NewsItem

BUILD_ID = "2026.10.15-editorial-audit-2"


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
