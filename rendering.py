"""Telegram Bot API 10.3 rich-message rendering and legacy fallback."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape

from news import NewsItem, TOPIC_ORDER, IMPACT


def e(value: str) -> str:
    return escape(str(value), quote=True)


def grouped(news: list[NewsItem]) -> dict[str, list[NewsItem]]:
    groups = defaultdict(list)
    for item in news:
        groups[item.topic].append(item)
    return groups


def rich_html(news: list[NewsItem], moment: datetime, summary_map: dict[str, tuple[str, str]] | None = None) -> str:
    summaries = summary_map or {}
    groups = grouped(news)
    date_label = moment.strftime("%d.%m.%Y · %H:%M МСК")
    parts = [
        "<h1>DRAGON NEWS</h1>",
        f"<p><b>{e(date_label)}</b> · {len(news)} публикаций</p>",
        "<blockquote>Россия, Липецк, законы, блокировки, финансы, СВО, IT и ПК-игры. "
        "Новости — сообщения указанных источников, а не независимая проверка каждого утверждения.</blockquote>",
        "<hr/>",
    ]
    for topic in TOPIC_ORDER:
        section = groups.get(topic, [])
        if not section and topic != "Липецк и Липецкая область":
            continue
        # Collapsed world and conflict reports, other sections immediately visible.
        is_open = topic not in ("СВО — позиции сторон", "Мир и экономика")
        attr = " open" if is_open else ""
        parts.append(f"<details{attr}><summary><b>{e(topic)}</b> · {len(section)}</summary>")
        if not section:
            parts.append("<p>Значимых свежих публикаций за период в доступных источниках не найдено.</p>")
        for index, article in enumerate(section, 1):
            summary, consequence = summaries.get(article.key, (article.summary, IMPACT.get(topic, "")))
            summary = summary or "В доступной ленте есть только заголовок: сведения требуют проверки в первоисточнике."
            label = f"{index}. {article.title.rsplit(' - ', 1)[0]}"
            parts.append(f"<h3>{e(label)}</h3>")
            parts.append(f"<p><i>{e(article.published.strftime('%d.%m, %H:%M МСК'))}" +
                         (f" · {e(article.viewpoint)}" if article.viewpoint else "") + "</i></p>")
            parts.append(f"<p>{e(summary[:950])}</p>")
            if consequence:
                parts.append(f"<p><b>Почему важно:</b> {e(consequence[:650])}</p>")
            parts.append(f'<p><a href="{e(article.link)}">Источник: {e(article.source)}</a></p>')
        parts.append("</details>")
        parts.append("<hr/>")
    parts.extend([
        "<h2>Что проверить сегодня</h2>",
        "<ul><li>Липецк: учитывать местные ограничения и адреса отключений из источников.</li>",
        "<li>Финансы: перепроверять даты вступления законов в силу и условия банков.</li>",
        "<li>VPN/IT: проверять критические изменения по официальным сообщениям.</li></ul>",
        "<footer>Публикации отобраны автоматически. Перепроверяйте важные утверждения в первоисточнике.</footer>",
    ])
    return "\n".join(parts)


def fallback_html(news: list[NewsItem], moment: datetime) -> list[str]:
    """Separate standard HTML messages (<4096 chars), if Rich API unavailable."""
    chunks = [f"<b>DRAGON NEWS · {e(moment.strftime('%d.%m.%Y'))}</b>\n"
              f"Свежих публикаций: {len(news)}\n"]
    for topic, entries in grouped(news).items():
        text = f"\n<b>{e(topic)}</b>\n"
        for item in entries:
            blurb = e((item.summary or "Подробности по ссылке.")[:240])
            piece = (f"\n<b>{e(item.title[:180])}</b>\n{blurb}\n"
                     f'<a href="{e(item.link)}">{e(item.source)}</a> · '
                     f"{e(item.published.strftime('%d.%m %H:%M'))}\n")
            if len(text) + len(piece) > 3200:
                chunks.append(text)
                text = f"<b>{e(topic)} (продолжение)</b>\n"
            text += piece
        if len(chunks[-1]) + len(text) < 3200:
            chunks[-1] += text
        else:
            chunks.append(text)
    return [x for x in chunks if x.strip()]


def export_markdown(news: list[NewsItem], moment: datetime) -> str:
    groups = grouped(news)
    parts = [f"# DRAGON NEWS — {moment.strftime('%d.%m.%Y %H:%M МСК')}", ""]
    for topic in TOPIC_ORDER:
        if topic not in groups:
            continue
        parts.append(f"## {topic}")
        for item in groups[topic]:
            parts.extend([f"### {item.title}",
                          f"{item.published.strftime('%d.%m.%Y %H:%M МСК')} — {item.source}",
                          item.summary or "Подробности по ссылке.",
                          f"Источник: {item.link}", ""])
    return "\n".join(parts)
