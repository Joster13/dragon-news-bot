"""Event-level deduplication and editorial scoring for Dragon News.

An RSS item is not necessarily a distinct news event: different publishers can
describe the same parliamentary vote or regulatory announcement with different
headlines. Prefer one article with richer context rather than repeated stories.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import urlsplit

NOISE_HEADLINE = re.compile(
    r"(?i)^(?:в\s+кремле\s+решили\s+умолчать|"
    r"песков\s+(?:не\s+)?(?:сказал|раскрыл|прокомментировал)|"
    r"посол\s+россии\s+.*\s+рассказал[а-я]*\s+о\s+ситуации|"
    r"председателем\s+\w+\s+правительства\s+назначили|"
    r"депутаты\s+поддержали\s+кандидатуру)"
)
STOP = frozenset((
    "в", "во", "на", "о", "об", "от", "по", "при", "для", "за", "с", "со",
    "к", "ко", "до", "и", "из", "не", "что", "это", "как", "же", "а",
    "гд", "госдума", "депутаты", "совет", "федерации",
    "россии", "россия", "рф", "российский",
    "одобрил", "одобрила", "приняла", "принял", "принято",
    "первом", "первое", "чтении", "чтение", "1", "i",
    "законопроект", "законопроекта", "проект", "проекта",
    "новые", "новый", "сообщили", "заявил", "рассказал",
    "сообщило", "стало", "известно", "данные", "закон",
))

NORMALIZATION = (
    ("централизованн", "централизованный"),
    ("правов", "правовой"),
    ("статус", "статус"),
    ("систем", "система"),
    ("обмен", "обмен"),
    ("недвижимост", "недвижимость"),
    ("маркиров", "маркировка"),
    ("банковск", "банк"),
    ("банк", "банк"),
    ("звонк", "звонок"),
    ("перевод", "перевод"),
    ("отлож", "отложить"),
    ("блокиров", "блокировка"),
    ("криптовалют", "криптовалюта"),
    ("цифров", "цифровой"),
    ("налог", "налог"),
)


def tokens(headline: str) -> frozenset[str]:
    words = re.findall(r"[а-яёa-z0-9]+", headline.lower())
    output = []
    for word in words:
        if word in STOP or len(word) <= 2 and not word.isdigit():
            continue
        for prefix, replacement in NORMALIZATION:
            if word.startswith(prefix):
                word = replacement
                break
        if word not in STOP:
            output.append(word)
    return frozenset(output)


def _actions(headline: str) -> str:
    h = headline.lower()
    if re.search(r"отклонил|отказал|не\s+поддержал|отменил", h):
        return "rejected"
    if re.search(r"принял|приняла|одобрил|одобрила|утвердил|подписал", h):
        return "approved"
    return ""


def _legislative_stage(headline: str) -> str:
    text = headline.lower()
    checks = (
        ("reading1", r"(?:^|\W)(?:i|1|первом|первое|первого)\s+чтен"),
        ("reading2", r"(?:^|\W)(?:ii|2|втором|второе|второго)\s+чтен"),
        ("reading3", r"(?:^|\W)(?:iii|3|третьем|третье|третьего)\s+чтен"),
        ("signed", r"подписал[а-я]*\s+закон|закон\s+подписан"),
    )
    for stage, pattern in checks:
        if re.search(pattern, text):
            return stage
    return ""


def _bill_id(item) -> set[str]:
    """Bill numbers in title/description can identify different legislative acts."""
    content = item.title + " " + (item.summary or "")
    return set(re.findall(r"(?<!\d)\d{5,}-\d{1,3}(?!\d)", content))


def _legislative_topic(item) -> str:
    """A small domain map for cases where two outlets use different species.

    This map only applies to one reading-stage and public funding context;
    it is not a generic claim that all fisheries bills concern one event.
    """
    content = (item.title + " " + (item.summary or "")).lower()
    if re.search(r"рыб|лосос|форел|аквакультур|рыбовод", content):
        if re.search(r"госзадан|государственн[а-я ]+задан|"
                     r"подведомственн[а-я ]+росрыболов", content):
            return "fisheries-state-breeding"
    return ""


def same_event(a, b) -> bool:
    """Conservative match of separate headlines describing the SAME event.

    Avoid matching unrelated news merely because a country or person repeats.
    """
    if a.topic != b.topic:
        return False
    stage_a, stage_b = _legislative_stage(a.title), _legislative_stage(b.title)
    if stage_a and stage_b and stage_a != stage_b:
        return False
    bills_a, bills_b = _bill_id(a), _bill_id(b)
    if bills_a and bills_b and bills_a.isdisjoint(bills_b):
        return False
    if (a.topic == "Законы и правила"
            and stage_a and stage_a == stage_b
            and _legislative_topic(a) == _legislative_topic(b)
            and _legislative_topic(a)):
        return True
    # Do not merge a later rejection with an earlier approval.
    action_a, action_b = _actions(a.title), _actions(b.title)
    if action_a and action_b and action_a != action_b:
        return False
    a_words, b_words = tokens(a.title), tokens(b.title)
    shared = a_words & b_words
    if len(shared) < 3:
        return False
    numbers_a = {w for w in a_words if w.isdigit()}
    numbers_b = {w for w in b_words if w.isdigit()}
    # Distinct bill numbers, years or other identifying values imply different events.
    if numbers_a and numbers_b and numbers_a != numbers_b:
        return False
    containment = len(shared) / min(len(a_words), len(b_words))
    jaccard = len(shared) / len(a_words | b_words)
    if containment >= .8 and jaccard >= .57:
        return True
    left = " ".join(sorted(a_words))
    right = " ".join(sorted(b_words))
    return SequenceMatcher(None, left, right).ratio() >= .86 and jaccard >= .48


def editorial_score(item) -> int:
    """Importance vs. filler. A low score is not a statement about factual truth."""
    title = item.title.lower()
    if NOISE_HEADLINE.search(item.title):
        return -5
    # Advice columns and non-substantive political soundbites are not updates.
    if re.search(
        r"(?i)назвал[а-я]*\s+(?:основны[а-я ]+точк[а-я ]+роста|"
        r"легальны[а-я ]+способ[а-я ]+сэкономить)|"
        r"назвал[а-я]*\s+побед[а-я ]+.*историческ|"
        r"высказал[а-я]*\s+об\s+угрозе|"
        r"в\s+европарламенте\s+высказал[а-я]*|"
        r"прокомментировал[а-я]*\s+идею",
        title,
    ):
        return -5
    if re.search(r"(?i)в\s+\w+ской\s+области.*назнач(?:ил|ен)|"
                 r"председател[а-я]+\s+\w+ского\s+правительств", title):
        return -2
    if re.search(r"(?i)умолчать|не\s+стал\s+раскрывать\s+список|"
                 r"где\s+отдохнуть|раскритиковал\s+заявлени", title):
        return -2
    score = 2
    # Regional-only social measures outside Lipetsk are low priority for a
    # national-and-Lipetsk digest; relevant items can still appear elsewhere.
    if item.topic == "Законы и правила":
        if re.search(r"(?i)^в\s+[а-яё-]+\s+(?:области|крае|республике)\b", title):
            if not re.search(r"липецк|елец|воронеж", title):
                score -= 3
    if item.summary and len(item.summary) >= 90:
        score += 1
    if re.search(r"принял|одобрил|утвердил|вступил|"
                 r"огранич|отключ|бпла|угроз|запрет|"
                 r"ставк|цб|законопроект|связь|"
                 r"уязвим|кибератак|налог|"
                 r"снижен|повышен", title):
        score += 3
    if item.topic == "Липецк и Липецкая область":
        score += 2
    if item.topic in ("Интернет и VPN", "Финансы и крипта", "Инфраструктура и безопасность"):
        score += 1
    if re.search(r"(?i)предположил|задумались|может|"
                 r"считает|мнение|рассказал|"
                 r"решили\s+умолчать", title):
        score -= 2
    # A press comment without a concrete decision or measurable development
    # should not displace significant policy or economic news.
    if re.search(r"(?i)\b(?:заявил|сказал|назвал|считает|высказался|призвал)\b", title):
        if not re.search(r"(?i)принял|утвердил|вступил|увеличил|снизил|"
                         r"начал|подписал|ввел|ввёл|поставки|"
                         r"отменил|ограничил|договор", title):
            score -= 1
    return score


def source_quality(item) -> int:
    domain = urlsplit(item.link).hostname or ""
    score = {
        "cbr.ru": 5,
        "www.cbr.ru": 5,
        "publication.pravo.gov.ru": 5,
        "tass.ru": 3,
        "www.interfax.ru": 3,
        "interfax.ru": 3,
        "ria.ru": 2,
    }.get(domain.lower(), 1)
    if item.summary:
        score += min(len(item.summary), 500) // 100
    return score


def deduplicate(items: list) -> list:
    """Select a single original source per group of equivalent articles."""
    ordered = sorted(items, key=lambda x: (editorial_score(x), source_quality(x), x.published.timestamp()), reverse=True)
    selected = []
    for candidate in ordered:
        if any(same_event(candidate, earlier) for earlier in selected):
            continue
        selected.append(candidate)
    return selected
