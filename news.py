"""Discover dated source-linked articles. No scraping behind paywalls.

Google News RSS is an aggregator and some item links lead through it to the
publisher. The bot never asserts that a Google News feed proves a claim.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET
import httpx

log = logging.getLogger(__name__)
TZ = ZoneInfo("Europe/Moscow")

@dataclass(frozen=True)
class NewsItem:
    topic: str
    title: str
    summary: str
    link: str
    source: str
    published: datetime
    viewpoint: str = ""

    @property
    def normalized_title(self) -> str:
        # Google News appends a publication name after the headline.
        base = self.title.rsplit(" - ", 1)[0]
        return re.sub(r"[^\w]+", "", base.lower())[:120]

    @property
    def key(self) -> str:
        return hashlib.sha256(self.normalized_title.encode()).hexdigest()

# Topics, Google News searches, approximate per-topic limits.
# Searches collect multiple independent publisher reports; they do NOT themselves
# independently verify the underlying events.
QUERIES = [
    ("Липецк и Липецкая область", 'Липецк область отключения ЖКХ тарифы дороги школы безопасность when:1d', 4, ""),
    ("Липецк и Липецкая область", 'site:gorod48.ru Липецк when:1d', 3, ""),
    ("Россия — главное", 'Россия экономика правительство цены крупные события when:1d', 3, ""),
    ("Законы и правила", 'Госдума принят закон законопроект налоги ограничения мобилизация when:1d', 3, ""),
    ("Интернет и VPN", 'РКН блокировка VPN Telegram VLESS ТСПУ интернет связь when:1d', 3, ""),
    ("Финансы и крипта", 'ЦБ банки ключевая ставка 115-ФЗ вклады ИИС USDT P2P санкции when:1d', 3, ""),
    ("СВО — позиции сторон", 'Минобороны РФ Украина фронт переговоры when:1d', 2, "Российские публикации"),
    ("СВО — позиции сторон", 'site:ukrinform.net Ukraine war update when:1d', 2, "Украинские публикации"),
    ("СВО — позиции сторон", 'site:reuters.com Ukraine Russia war when:1d', 2, "Международные публикации"),
    ("Мир и экономика", 'world geopolitics sanctions EU China USA global economy when:1d', 2, ""),
    ("IT, облака и AI", 'Microsoft Google OpenAI ChatGPT Yandex VK major release when:1d', 3, ""),
    ("Инфраструктура и безопасность", 'critical vulnerability exploited CISA server cloud data breach when:1d', 2, ""),
    ("Игры на ПК", 'Steam PC game release Russian localization major update when:1d', 2, ""),
]
TOPIC_ORDER = [
    "Липецк и Липецкая область", "Россия — главное", "Законы и правила",
    "Интернет и VPN", "Финансы и крипта", "СВО — позиции сторон",
    "Мир и экономика", "IT, облака и AI", "Инфраструктура и безопасность",
    "Игры на ПК",
]
IMPACT = {
    "Липецк и Липецкая область": "Может затрагивать жителей Липецка и области; уточняйте адреса, сроки и решения местных властей.",
    "Россия — главное": "Может повлиять на экономику и повседневные расходы в России.",
    "Законы и правила": "Проверьте, принят ли акт и когда он вступит в силу: законопроект ещё не закон.",
    "Интернет и VPN": "Для VPN-поддержки нужно проверить доступность по регионам и операторам; сообщения о сбоях не всегда означают блокировку.",
    "Финансы и крипта": "При переводах и P2P учитывайте требования банков и сохраняйте документы о происхождении средств.",
    "СВО — позиции сторон": "Военные данные сторон могут расходиться, поэтому цифры и заявления требуют независимой проверки.",
    "Мир и экономика": "Может затронуть санкции, зарубежные платежи, логистику и импортное оборудование.",
    "IT, облака и AI": "Проверьте доступность новых функций, тарифы и условия использования в России.",
    "Инфраструктура и безопасность": "Если упомянутая система есть в инфраструктуре, изучите бюллетень производителя и обновления.",
    "Игры на ПК": "Перед покупкой уточните фактический релиз, поддержку русского языка и региональную доступность.",
}

BAD_WORDS = ("футбол", "хоккей", "чемпионат", "теннис", "спартак", "селебрити", "звезда шоу", "свадьба пев", "гороскоп")


def clean_snippet(raw: str) -> str:
    raw = re.sub(r"<[^>]+>", " ", raw or "")
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()[:650]


def news_rss_url(query: str) -> str:
    return "https://news.google.com/rss/search?" + urlencode({"q": query, "hl": "ru", "gl": "RU", "ceid": "RU:ru"})


def decode_feed(topic: str, viewpoint: str, payload: bytes, now: datetime, age_hours: float = 27) -> list[NewsItem]:
    """Parse dated RSS 2.0 records without external scraping or nonstandard dependencies."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    items = root.findall("./channel/item")
    found = []
    min_dt = now - timedelta(hours=age_hours)
    for entry in items:
        try:
            date_value = (entry.findtext("pubDate") or "").strip()
            if not date_value:
                continue  # No date => exclude.
            d = parsedate_to_datetime(date_value)
            if d.tzinfo is None:
                continue
            d = d.astimezone(now.tzinfo)
            if not (min_dt <= d <= now + timedelta(minutes=5)):
                continue
            title = clean_snippet(entry.findtext("title") or "")[:240]
            url = (entry.findtext("link") or "").strip()
            if not title or urlparse(url).scheme != "https":
                continue
            if any(w in title.lower() for w in BAD_WORDS):
                continue
            source_node = entry.find("source")
            source = clean_snippet(source_node.text or "") if source_node is not None else ""
            if not source and " - " in title:
                source = title.rsplit(" - ", 1)[-1]
            if not source:
                source = urlparse(url).hostname or "Издание"
            descr = clean_snippet(entry.findtext("description") or "")
            descr = descr.replace("View Full Coverage", "").strip()
            if descr.lower() == title.lower():
                descr = ""
            found.append(NewsItem(topic, title, descr, url, source[:70], d, viewpoint))
        except (ValueError, OverflowError, TypeError):
            continue
    return found


async def collect_news(client: httpx.AsyncClient, now: datetime, seen: set[str], max_items: int = 28) -> tuple[list[NewsItem], int]:
    limit = asyncio.Semaphore(4)

    async def one(topic: str, query: str, take: int, viewpoint: str):
        async with limit:
            try:
                r = await client.get(news_rss_url(query), timeout=18)
                r.raise_for_status()
                return (topic, take, decode_feed(topic, viewpoint, r.content, now), True)
            except (httpx.HTTPError, ValueError) as e:
                log.warning("RSS fetch failed for %s: %s", topic, e)
                return (topic, take, [], False)

    results = await asyncio.gather(*(one(*q) for q in QUERIES))
    success_count = sum(ok for _, _, _, ok in results)
    # First pass: per query limit. Then cap total by priority topic order.
    candidates = {}
    unique = set(seen)
    for topic, take, entries, _ in results:
        candidates.setdefault(topic, [])
        count = 0
        for a in sorted(entries, key=lambda x: x.published, reverse=True):
            if a.key not in unique:
                candidates[topic].append(a)
                unique.add(a.key)
                count += 1
            if count >= take:
                break
    # Round-robin fills important sections before expanding any section.
    selected: list[NewsItem] = []
    indexes = {t: 0 for t in TOPIC_ORDER}
    while len(selected) < max_items:
        progressed = False
        for topic in TOPIC_ORDER:
            idx = indexes[topic]
            if idx < len(candidates.get(topic, [])) and len(selected) < max_items:
                selected.append(candidates[topic][idx])
                indexes[topic] += 1
                progressed = True
        if not progressed:
            break
    return selected, success_count
