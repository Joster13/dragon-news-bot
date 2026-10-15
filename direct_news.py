"""Dragon News: direct publisher RSS and public regional Telegram channel.

No Google News link decoding. Publisher summaries and original URLs are the
primary source; optional page enrichment can add detail but never delete news.
All network errors are counted and shown by /sources.
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from news import NewsItem, TOPIC_ORDER
from editorial import deduplicate, editorial_score, same_event
from editorial_gate import is_publishable

log = logging.getLogger("dragon-news.sources")

@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    hint: str = ""

FEEDS = (
    Feed("Интерфакс", "https://www.interfax.ru/rss"),
    Feed("ТАСС", "https://tass.ru/rss/v2.xml"),
    Feed("Коммерсантъ", "https://www.kommersant.ru/RSS/news.xml"),
    Feed("РБК", "https://rssexport.rbc.ru/rbcnews/news/30/full.rss"),
    Feed("РИА Новости", "https://ria.ru/export/rss2/archive/index.xml"),
    Feed("Известия", "https://iz.ru/xml/rss/all.xml"),
    Feed("Лента.ру", "https://lenta.ru/rss/"),
    Feed("Газета.Ru", "https://www.gazeta.ru/export/rss/lenta.xml"),
    Feed("Хабр", "https://habr.com/ru/rss/news/?fl=ru", "IT, облака и AI"),
    Feed("BBC Russian", "https://feeds.bbci.co.uk/russian/rss.xml"),
    Feed("Deutsche Welle", "https://rss.dw.com/xml/rss-ru-all"),
    Feed("GOROD48", "https://t.me/s/gorod48ru", "Липецк и Липецкая область"),
)

# Documented direct sources with actual article links. Exclude advertising,
# routine traffic accidents, entertainment, sports and generic clickbait.
NOISE = re.compile(
    r"футбол|хоккей|турнир|спортсмен|олимпиад|чемпионат|концерт|фестивал|"
    r"звезд[аы] шоу|звёзд[аы] шоу|гороскоп|розыгрыш|промокод|скидк|"
    r"рецепт|кулинар|театральн|актрис|певиц|топ[- ]?10|"
    r"дтп|столкновени[ея] автомобил|дорожн[а-я ]+авари[яю]|"
    r"задержан водитель|разбил машин|пьяный водитель|"
    r"какое решение примет|что будет, если|что будет если|"
    r"авари[яи].*(?:автомобил|машин|водител|ваз|лада|ауди)|"
    r"(?:автомобил|машин).*(?:врезал|столкнул|сбил)|"
    r"врезал[а-я ]+в[а-я ]+(?:автомобил|машин)|"
    r"раскритиковал|прокомментировал идею|"
    r"высказался об инициативе|оппозици[яю].*агитк|"
    r"\bпредр[её]к\b|\bпредсказал\b|\bвклад\b.{0,60}первичн|"
    r"(?:^|\b)(?:\d+|пять|семь)\s+статей\s+(?:октября|недели|месяца)|"
    r"психологи[яи]\s+реклам[ыа]|обзор\s+статей|"
    r"эксперты рассказали[,]? запретят ли|"
    r"предложили размещать дата-центры в отработанных|"
    r"(?:пытал[аиы]?|пытали|избил[аиы]?|вымогател[аиы]?|"
    r"предстал[аи]? перед судом).{0,60}(?:автомойк|подростк)|"
    r"(?:подростк|автомойк).{0,60}(?:вымогател|судом|пытал)|"
    r"названы\s+(?:три|пять|семь|\d+)\s+главн[а-я ]+\s+правил|"
    r"формировани[ея]\s+финансов[а-я ]+\s+подушк|"
    r"россиянам\s+рассказали\s+о\s+праве\s+банк[а-я]*\s+аннулироват|"
    r"как\s+(?:сформироват|создат|накопит)\s+финансов[а-я ]+подушк|"
    r"книг[аиуы]?\s+в\s+Британию|книжны[а-я ]+магазин|"
    r"писательниц[аы].*книг|"
    r"воскрешени[еяя].*умерших\s+акт[её]р|"
    r"акт[её]р[а-я]*\s+с\s+помощью\s+ИИ|"
    r"в\s+России\s+предложили\s+возводить\s+дата-центр|"
    r"(?:классическ[а-я ]+квест|квест.{0,60}1999\s+год)",
    re.I,
)

LOCAL = re.compile(
    r"липецк|липецк[а-я]+ област|елец|гряз[а-я]+|данков|"
    r"усман|лебедян|задонск|чаплыгин|тербун|хлевн",
    re.I,
)
LOCAL_IMPORTANT = re.compile(
    r"водоснабж|водопровод|водоканал|без воды|подач[а-я ]+воды|"
    r"отключ|отоплен|электр|аварийн|школ|больниц|"
    r"дорог|транспорт|перекры|ремонт|бпла|сирен|опасност|"
    r"пожар на завод|льгот|выплат|зарплат|тариф|цен[аы]|"
    r"трудоустрой|предприяти|производств|налог|связь|интернет|"
    r"строител|подключ|маршрут|лифтов|медицин|образован|"
    r"бюджет|жкх|водоснабж|военн",
    re.I,
)
VPN = re.compile(
    r"\bVPN\b|\bVLESS\b|\bDPI\b|\bТСПУ\b|\bРКН\b|"
    r"роскомнадзор|телеграм|telegram|youtube|ютуб|"
    r"блокировк[а-я ]+(?:интернет|сайт|мессенджер|VPN|доступ)|"
    r"(?:мобильн|домашн|проводн)[а-я ]+интернет|"
    r"интернет[- ]?провайдер|протокол[а-я ]+связи",
    re.I,
)
# Financial classification must not be triggered solely by "рублей" in
# procurement figures or "ЦБ" commenting on agriculture.
FINANCE = re.compile(
    r"\bбанк(?:и|ов|ах|ам|а|е|ом|овский|овские|овскую)?\b|"
    r"банковск|центробанк|\bЦБ\b|"
    r"ключев[а-я ]+ставк|процентн[а-я ]+ставк|"
    r"(?<![а-яё])вклад(?:ы|ов|ах|ами|а|е|ом)?\b|депозит[а-я]*|кредит[а-я]*|ипотек[а-я]*|"
    r"инфляц[а-я]*|бирж[а-я]*|криптовалют|"
    r"биткоин|\bBTC\b|\bUSDT\b|\bP2P\b|"
    r"денежн[а-я ]+перевод|банковск[а-я ]+перевод|"
    r"финансов[а-я]*|валютн[а-я]*|курс[а-я ]+рубл",
    re.I,
)
FINANCE_SUBJECT = re.compile(
    r"ставк|вклад|депозит|кредит|ипотек|инфляц|денежн|"
    r"рубл|финанс|плат[её]ж|перевод|инвест|валют|"
    r"банков|бирж|сбережен|процент",
    re.I,
)
FINANCE_CONTEXT = re.compile(
    r"криптовалют|\bP2P\b|\bUSDT\b|банковск|"
    r"денежн[а-я ]+перевод|валютн[а-я]*|плат[её]ж[а-я]*|"
    r"кредит[а-я]*|(?<![а-яё])вклад(?:ы|ов|ах|ами|а|е|ом)?\b|"
    r"(?<![а-яё])банк(?:и|ов|ах|ам|а|е|ом|овский|овские)?\b",
    re.I,
)
NATIONAL_IMPORTANT = re.compile(
    r"правительств|минфин|минпромторг|экономик|"
    r"производств|энергетик|экспорт|импорт|"
    r"бюджет|тариф|отрасл|инфраструктур|"
    r"реформ|завод|строител|занятост|"
    r"налог|зарплат|жиль|топлив|"
    r"постановлен|утвердил|государственн[а-я ]+программ",
    re.I,
)

# Mentions of the Duma or State Council are not themselves legal developments.
LAW = re.compile(
    r"законопроект|федеральн[а-я ]+закон|"
    r"постановлени[ея]|новы[а-я ]+правил[ао]|"
    r"госпошлин|налогов[а-я ]+вычет|"
    r"(?:госдум[а-я]*|\bГД\b)[а-я ,.]{0,35}(?:принял|приняла|одобрил|одобрила|"
    r"рассмотрит|внесл|утверди)|"
    r"правительств[а-я ]+(?:принял|приняло|утвердило|утвердил)|"
    r"вступ[а-я ]+в\s+силу",
    re.I,
)
CYBER = re.compile(
    r"\bCVE-\d|уязвимост|кибератак|взлом|шифровальщик|"
    r"утечк[а-я ]+данных|дата[- ]?центр|"
    r"сервер[а-я ]+(?:взлом|атак|сбо)|ransomware",
    re.I,
)
IT = re.compile(
    r"OpenAI|ChatGPT|Google|Microsoft|Windows|"
    r"Яндекс|нейросет|искусственн[а-я ]+интеллект|"
    r"\bИИ\b|\bAI\b|облачн[а-я ]+сервис|"
    r"процессор|видеокарт|NVIDIA|\bAMD\b|\bIntel\b|"
    r"Apple Intelligence|\bApple\b.{0,24}\bAI\b|"
    r"Linux|платформ[а-я ]+разработ",
    re.I,
)
GAMES = re.compile(r"steam|видеоигр|компьютерн[а-я ]+игр|игр[аы] на пк|релиз игр", re.I)
WORLD = re.compile(
    r"США|Китай|Евросоюз|Европарламент|Герман|Франци|"
    r"Британи|Израил|Иран|ООН|ОПЕК|международн|"
    r"санкц|нефт[а-я]*|Ормуз|Ближн[а-я ]+Восток",
    re.I,
)
WAR = re.compile(
    r"Украин|\bСВО\b|\bВСУ\b|Минобороны РФ|фронт|"
    r"военн[а-я ]+операц|беспилотник|БПЛА|"
    r"прекращени[ея] огня|мирн[а-я ]+переговор",
    re.I,
)
RUSSIA = re.compile(
    r"Российск|России|Россия|РФ\b|"
    r"Минфин|Минпромторг|Правительств|"
    r"Госдум|Федеральн[а-я ]+|"
    r"экономик[а-я ]+России",
    re.I,
)
STATUS: list[dict[str, str | int]] = []


def clean(raw: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)).strip()


def has_details(title: str, desc: str) -> bool:
    if not desc or len(desc) < 38:
        return False
    norm = lambda s: re.sub(r"[^а-яёa-z0-9]", "", s.lower())
    a, b = norm(title), norm(desc)
    return bool(b) and b != a and not b.startswith(a)


def category(title: str, description: str = "", forced: str = "") -> str | None:
    value = title.strip()
    if not value or NOISE.search(value):
        return None
    # Evergreen advice and political rhetoric are not newly enacted policies.
    if re.search(
        r"(?i)побед[а-я ]+.*(?:историческ|на\s+выборах)|"
        r"россиянам\s+назвали\s+легальны[а-я ]+способ[а-я ]+сэкономить|"
        r"назвали\s+основны[а-я ]+точк[а-я ]+роста|"
        r"в\s+европарламенте\s+высказались|"
        r"в\s+госдуме\s+прокомментировали\s+идею|"
        r"совет[а-я ]+как\s+сэкономить",
        value,
    ):
        return None
    # Financial and war keywords must denote an actual subject, not be
    # character substrings inside unrelated Russian words.
    if re.search(r"(?i)\bпауэрбанк(?:и|ов|ам|ах)?\b", value):
        return None
    if forced == "Липецк и Липецкая область":
        if not LOCAL_IMPORTANT.search(value):
            return None
        return forced
    if LOCAL.search(value):
        return "Липецк и Липецкая область" if LOCAL_IMPORTANT.search(value) else None
    # Policy for veterans/families is social legislation, not a combat update.
    if re.search(r"(?i)льгот|пошлин|налог|соц(?:иальн)?[а-я ]+выплат|пенси", value) and re.search(
        r"(?i)\bСВО\b|ветеран|вдов|военнослужащ|мобилизованн", value
    ):
        return "Законы и правила"
    if LAW.search(value):
        return "Законы и правила"
    # Starlink / Starshield coverage may omit Ukraine from the headline.
    if re.search(r"(?i)starshield|starlink", value) and re.search(
        r"(?i)украин|\bВСУ\b|на\s+фронте|военн[а-я ]+использован", description
    ):
        return "СВО — позиции сторон"
    if WAR.search(value):
        return "СВО — позиции сторон"
    if VPN.search(value):
        return "Интернет и VPN"
    if FINANCE.search(value):
        # The central bank can also report on agricultural production.
        central_only = re.search(r"\bЦБ\b|центробанк", value, re.I)
        if not central_only or FINANCE_SUBJECT.search(value):
            return "Финансы и крипта"
    # A generic headline like "В России запретят один вид сделок" can
    # still be classified from a substantive publisher description.
    if re.search(r"сделк|перевод|плат[её]ж|огранич|запрет", value, re.I) and FINANCE_CONTEXT.search(description):
        return "Финансы и крипта"
    if CYBER.search(value):
        return "Инфраструктура и безопасность"
    if GAMES.search(value):
        return "Игры на ПК"
    if IT.search(value):
        if re.search(r"скидк|промокод|даром|бесплатн[а-я ]+токен", value, re.I):
            return None
        return "IT, облака и AI"
    if WORLD.search(value):
        return "Мир и экономика"
    # The word "Russia" alone is not newsworthy.
    if RUSSIA.search(value) and NATIONAL_IMPORTANT.search(value):
        return "Россия — главное"
    return None


def rss_items(feed: Feed, payload: bytes, now: datetime, window_h: int = 30) -> list[NewsItem]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise ValueError("invalid RSS/Atom XML")
    elements = root.findall("./channel/item")
    atom = False
    if not elements:
        atom = True
        elements = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    output = []
    start = now - timedelta(hours=window_h)
    for entry in elements[:180]:
        tag = lambda key: entry.findtext(key) or ""
        try:
            if atom:
                ns = "{http://www.w3.org/2005/Atom}"
                title = clean(tag(ns+"title"))
                stamp = tag(ns+"published") or tag(ns+"updated")
                link_el = entry.find(ns+"link")
                url = link_el.get("href", "") if link_el is not None else ""
                desc = clean(tag(ns+"summary") or tag(ns+"content"))
            else:
                title = clean(tag("title"))
                stamp = tag("pubDate")
                url = tag("link").strip()
                desc = clean(tag("description") or tag("{http://purl.org/rss/1.0/modules/content/}encoded"))
            if not title or not url.startswith("https://"):
                continue
            if atom:
                dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            else:
                dt = parsedate_to_datetime(stamp)
            if dt.tzinfo is None:
                continue
            dt = dt.astimezone(now.tzinfo)
            if not start <= dt <= now + timedelta(minutes=5):
                continue
            topic = category(title, desc, feed.hint)
            if not topic:
                continue
            if not has_details(title, desc):
                desc = ""
            else:
                # Public RSS factual text, not invented extrapolation.
                desc = desc[:650]
            viewpoint = ""
            if topic == "СВО — позиции сторон":
                viewpoint = {
                    "BBC Russian": "Британское издание",
                    "Deutsche Welle": "Немецкое издание",
                }.get(feed.name, "Российское издание")
            output.append(NewsItem(topic, title[:250], desc, url, feed.name, dt, viewpoint))
        except (ValueError, OverflowError, TypeError):
            continue
    return output


def telegram_items(feed: Feed, page: str, now: datetime, window_h: int = 30) -> list[NewsItem]:
    soup = BeautifulSoup(page, "html.parser")
    output = []
    for widget in soup.select(".tgme_widget_message[data-post]"):
        message_id = widget.get("data-post", "")
        text_node = widget.select_one(".tgme_widget_message_text")
        time_node = widget.select_one("time[datetime]")
        if not message_id or not text_node or not time_node:
            continue
        try:
            dt = datetime.fromisoformat(time_node["datetime"].replace("Z", "+00:00")).astimezone(now.tzinfo)
        except (KeyError, ValueError):
            continue
        if not (now - timedelta(hours=window_h) <= dt <= now + timedelta(minutes=5)):
            continue
        message = clean(text_node.get_text(" ", strip=True))
        message = re.sub(r"Прислать новость, связаться с редакцией.*$", "", message).strip()
        if len(message) < 90:
            continue
        headline = re.split(r"(?<=[.!?])\s+", message, maxsplit=1)[0][:210]
        if len(headline) < 30:
            headline = message[:130]
        topic = category(headline, message, feed.hint)
        if not topic:
            continue
        # If only the post headline is available, do not duplicate it as a description.
        tail = message[len(headline):].lstrip(" .!?\n")
        desc = tail[:650] if len(tail) >= 45 else message[:350]
        output.append(NewsItem(topic, headline, desc, "https://t.me/"+message_id, feed.name, dt))
    return output


def _rank(item: NewsItem) -> tuple[int, float]:
    important = re.compile(r"принял|утвердил|вступил|повысил|снизил|изменил|"
                           r"отключ|запрет|огранич|бпла|аварийн|закон|уязвим", re.I)
    score = 3 if important.search(item.title) else 1
    if item.summary:
        score += 1
    return score, item.published.timestamp()


def select_balanced(items: list[NewsItem], max_items: int, seen: set[str], recent_events=()) -> list[NewsItem]:
    by_topic = defaultdict(list)
    keys = set(seen)
    # Keep one representative per event, not one article per publisher.
    # Remove low-value filler instead of forcing 20-30 entries.
    # Filter eligibility BEFORE deduplication, so a poor first article cannot
    # suppress a useful second article about the same event.
    eligible = [item for item in items if is_publishable(item)]
    log.info("Editorial gate: %d/%d eligible", len(eligible), len(items))
    for item in deduplicate(eligible):
        if item.key in keys:
            continue
        if recent_events and any(same_event(item, old) for old in recent_events):
            continue
        # Do not publish military assertions as headline-only news.
        if item.topic == "СВО — позиции сторон" and len(item.summary.strip()) < 35:
            continue
        if item.topic == "Инфраструктура и безопасность" and re.search(
            r"(?i)отч[её]т\s+о\s+динамике|предложил[а-я]*\s+размещать\s+дата-центр",
            item.title,
        ):
            continue
        minimum = 4 if item.topic in ("Россия — главное", "Законы и правила", "Мир и экономика") else 2
        if editorial_score(item) < minimum:
            continue
        # Variety of independently published stories: prevent one outlet from
        # filling whole national/war sections with opinion pieces.
        if item.topic != "Липецк и Липецкая область":
            if sum(entry.source == item.source for entry in by_topic[item.topic]) >= 2:
                continue
        keys.add(item.key)
        by_topic[item.topic].append(item)
    capacity = {
        "Липецк и Липецкая область": 5, "Россия — главное": 4,
        "Законы и правила": 3, "Интернет и VPN": 4,
        "Финансы и крипта": 4, "СВО — позиции сторон": 3,
        "Мир и экономика": 3, "IT, облака и AI": 4,
        "Инфраструктура и безопасность": 3, "Игры на ПК": 2,
    }
    picked = []
    # Ensure local news gets priority even if the feeds contain many national items.
    for topic in TOPIC_ORDER:
        for item in by_topic[topic][:capacity.get(topic, 3)]:
            if len(picked) < max_items:
                picked.append(item)
    return picked[:max_items]


async def collect_news(client: httpx.AsyncClient, now: datetime, seen: set[str],
                       max_items: int = 28, recent_events=()) -> tuple[list[NewsItem], int]:
    sem = asyncio.Semaphore(6)

    async def fetch(feed: Feed):
        async with sem:
            try:
                r = await client.get(feed.url, timeout=12,
                                     headers={"Accept": "application/rss+xml, application/xml, text/xml, text/html"})
                r.raise_for_status()
                rows = telegram_items(feed, r.text, now) if feed.url.startswith("https://t.me/") else rss_items(feed, r.content, now)
                return feed.name, rows, "OK"
            except (httpx.HTTPError, ValueError, UnicodeError) as exc:
                return feed.name, [], type(exc).__name__

    fetched = await asyncio.gather(*(fetch(f) for f in FEEDS))
    global STATUS
    STATUS = [{"source": name, "status": status, "recent": len(items)}
              for name, items, status in fetched]
    reachable = sum(status == "OK" for _, _, status in fetched)
    all_items = [item for _, rows, _ in fetched for item in rows]
    ready = select_balanced(all_items, max_items, seen, recent_events)
    log.info("Direct news: reachable=%d/%d, relevant=%d, selected=%d",
             reachable, len(FEEDS), len(all_items), len(ready))
    return ready, reachable


async def enrich_optional(client: httpx.AsyncClient, items: list[NewsItem]) -> list[NewsItem]:
    """Try to improve very short summaries but NEVER throw items away."""
    sem = asyncio.Semaphore(6)
    async def one(item):
        if len(item.summary) >= 180 or item.link.startswith("https://t.me/"):
            return item
        async with sem:
            try:
                r = await client.get(item.link, timeout=7)
                r.raise_for_status()
                if "html" not in r.headers.get("content-type", "") or len(r.content) > 1_500_000:
                    return item
                soup = BeautifulSoup(r.text, "html.parser")
                description = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name": "description"})
                detail = clean(description.get("content", "")) if description else ""
                if len(detail) < 110:
                    block = soup.find("article") or soup.find("main")
                    if block:
                        detail = clean(" ".join(p.get_text(" ", strip=True) for p in block.find_all("p")[:3]))
                if len(detail) > len(item.summary) + 30:
                    # Limit verbatim text from the source; keep a short factual digest.
                    sentences = re.split(r"(?<=[.!?])\s+", detail)
                    extract = " ".join(sentences[:2])
                    extract = " ".join(extract.split()[:48])
                    return replace(item, summary=extract)
            except (httpx.HTTPError, ValueError, UnicodeError):
                pass
        return item
    return list(await asyncio.gather(*(one(i) for i in items)))


def source_report() -> str:
    if not STATUS:
        return "Источники ещё не проверялись. Отправь /preview."
    rows = ["Источники DRAGON NEWS (последняя проверка):"]
    for item in STATUS:
        rows.append(f"{item['source']}: {item['status']}, свежих по фильтрам — {item['recent']}")
    rows.append("Проверка каждого источника независима; сбой одного не блокирует остальные.")
    return "\n".join(rows)
