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
    # Shorter OR-based queries avoid rejecting all recent articles.
    ("Липецк и Липецкая область", '(Липецк OR "Липецкая область" OR Елец) (отключение OR отопление OR тарифы OR дороги OR безопасность OR выплаты) when:1d', 5, ""),
    ("Липецк и Липецкая область", 'site:gorod48.ru (Липецк OR область) when:1d', 5, ""),
    ("Россия — главное", 'Россия (экономика OR правительство OR цены OR промышленность) when:1d', 4, ""),
    ("Россия — главное", 'site:interfax.ru Россия (решение OR рост OR снижение) when:1d', 3, ""),
    ("Законы и правила", '(Госдума OR правительство) (закон OR постановление OR налог OR льготы) when:1d', 4, ""),
    ("Интернет и VPN", '(Роскомнадзор OR РКН OR VPN OR Telegram OR VLESS OR блокировка) when:1d', 4, ""),
    ("Финансы и крипта", '(ЦБ OR банки OR ставка OR вклады OR USDT OR P2P) (Россия OR рубль) when:1d', 4, ""),
    ("Финансы и крипта", '(санкции OR криптовалюта OR переводы) (банк OR биржа OR Россия) when:1d', 3, ""),
    ("СВО — позиции сторон", '(Минобороны OR фронт OR Украина OR переговоры) when:1d', 3, "Российские публикации"),
    ("СВО — позиции сторон", 'site:ukrinform.net (Russia OR Ukraine) when:1d', 2, "Украинские публикации"),
    ("СВО — позиции сторон", 'site:reuters.com (Ukraine OR Russia) when:1d', 2, "Международные публикации"),
    ("Мир и экономика", '(world OR EU OR China OR USA) (sanctions OR economy OR trade OR security) when:1d', 4, ""),
    ("IT, облака и AI", '(Microsoft OR Google OR OpenAI OR ChatGPT OR Yandex OR VK) (release OR update OR API OR AI) when:1d', 4, ""),
    ("Инфраструктура и безопасность", '(CISA OR CVE OR cyberattack OR ransomware) (critical OR exploited OR servers) when:1d', 4, ""),
    ("Игры на ПК", '(Steam OR PC) (release OR launched OR delayed OR localization) when:1d', 3, ""),
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
# Exclude routine local crime and speculative opinion pieces.
LOCAL_NOISE = ("дтп", "водитель", "угнал", "пьяный", "избил", "подрал", "кража", "задержали", "похитил", "разбил машин")
SPECULATION = ("что будет, если", "что будет если", "какое решение примет", "три сценария", "пять сценариев")
REGION_WORDS = ("липецк", "липецкой", "липецкая", "елец", "гряз", "задонск", "данков", "лебедян", "усман", "чаплыгин", "добрин", "тербун", "хлевн")
IMPORTANT_LOCAL = ("отключ", "водоснаб", "отоплен", "тариф", "дорог", "перекры", "свет", "школ", "поликлин", "льгот", "сирен", "опасност", "бпла", "аэропорт", "электроэнерг", "автобус", "бюджет", "завод", "интернет", "связь", "производств")


def is_significant(item: NewsItem) -> bool:
    title = item.title.rsplit(" - ", 1)[0].lower()
    if any(word in title for word in BAD_WORDS + SPECULATION):
        return False
    if item.topic == "Липецк и Липецкая область":
        if any(word in title for word in LOCAL_NOISE):
            return False
        # Regional source alone does not make a nationwide report a local event.
        if "в рф" in title or "в россии" in title:
            return False
        locality = any(word in title for word in REGION_WORDS)
        meaningful_local = any(word in title for word in IMPORTANT_LOCAL)
        return locality or meaningful_local
    return True


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
            # RSS descriptions often contain only the article headline and publisher.
            # Never pass them off as evidence-rich editorial summaries.
            normalized = lambda v: re.sub(r"[^\\w]+", "", v.lower())
            headline = normalized(title.rsplit(" - ", 1)[0])
            excerpt = normalized(descr)
            if not descr or len(descr) < 70 or (headline and (excerpt.startswith(headline) or headline in excerpt)):
                descr = ""
            article = NewsItem(topic, title, descr, url, source[:70], d, viewpoint)
            if is_significant(article):
                found.append(article)
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
