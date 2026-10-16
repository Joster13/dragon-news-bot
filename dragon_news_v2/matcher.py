"""Conservative event matching: same / possible / different, with named reasons."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Literal
from .models import Article

Decision = Literal['same','possible','different']

@dataclass(frozen=True)
class MatchResult:
    decision: Decision
    reason_codes: tuple[str, ...]

@dataclass(frozen=True)
class EventGroup:
    event_key: str
    stage: str
    article_ids: tuple[str, ...]
    title: str
    category_hint: str
    published_at: datetime | None = None
    excerpt: str = ''

BILL_ID = re.compile(r'(?<!\d)(?:№\s*)?(\d{5,}-\d{1,3})(?!\d)')
CVE_ID = re.compile(r'\bCVE-\d{4}-\d{4,}\b', re.I)
# Distinctive document-free event anchors. Deliberately narrow: these are
# candidate matches only after the existing stage/action conflict checks.
TECH_LEVY = re.compile(r'технологич[а-яё]*\s+сбор', re.I)
ELECTRONICS = re.compile(r'электрон[а-яё]*', re.I)
P2P_BAN = re.compile(r'\bp2p\b', re.I)
CRYPTO = re.compile(r'криптовалют[а-яё]*|криптоактив[а-яё]*', re.I)
BAN = re.compile(r'запрет[а-яё]*|запрещ[а-яё]*', re.I)
DATE_IN_TEXT = re.compile(
    r'\b([0-3]?\d)\s+(января|февраля|марта|апреля|мая|июня|июля|августа|'
    r'сентября|октября|ноября|декабря)\s+(20\d{2})\b', re.I
)
STAGE_RULES = (
    ('reading1', r'\b(?:i|1|первом|первое|первого)\s+чтен'),
    ('reading2', r'\b(?:ii|2|втором|второе|второго)\s+чтен'),
    ('reading3', r'\b(?:iii|3|третьем|третье|третьего)\s+чтен'),
    ('signed', r'\b(?:подписал\w*\s+закон|закон\s+подписан)'),
    ('effective', r'\b(?:вступил\w*\s+в\s+силу|начал\w*\s+действовать)'),
)
ACTION_RULES = (
    ('rejected', r'\b(?:отклонил\w*|отказал\w*|отменил\w*|не\s+поддержал\w*)'),
    ('proposed', r'\b(?:предложил\w*|вн[её]с\w*\s+законопроект|планируют\w*)'),
    ('approved', r'\b(?:принял\w*|одобрил\w*|утвердил\w*|подписал\w*)'),
    ('limited', r'\b(?:ограничил\w*|заблокировал\w*|отключил\w*)'),
    ('restored', r'\b(?:восстановил\w*|разблокировал\w*|возобновил\w*)'),
)
STOP = frozenset({'и','в','во','о','об','на','для','от','с','со','по','к','из','у','при','за','а','не','но',
                  'новый','новые','новым','россия','рф','госдума','депутаты','новости','сообщили',
                  'втором','первом','третьем','первое','второе','чтении','чтение','законопроект','проекта'})
NORMALIZE = {'ркн':'роскомнадзор','гд':'госдума','одобрили':'приняли',
             'приняла':'приняли','принял':'приняли','ограничена':'ограничил',
             'сервиса':'сервис','сервису':'сервис', 'пользователей':'пользователь',
             'поправки':'поправка','поправок':'поправка','проекта':'проект'}
GENERIC = {'роскомнадзор','ограничил','сервис','доступ','закон','изменил',
           'приняли','проект','банк','банки','решение','система'}


def stage(title: str) -> str:
    text=title.casefold()
    for name,pattern in STAGE_RULES:
        if re.search(pattern,text,re.I):
            return name
    return ''


def action(title: str) -> str:
    text=title.casefold()
    for name,pattern in ACTION_RULES:
        if re.search(pattern,text,re.I):
            return name
    return ''


def bills(article: Article) -> frozenset[str]:
    return frozenset(BILL_ID.findall(article.title + ' ' + article.excerpt))


def cves(article: Article) -> frozenset[str]:
    return frozenset(x.upper() for x in CVE_ID.findall(article.title + ' ' + article.excerpt))


def subject_tokens(article: Article) -> frozenset[str]:
    text=re.sub(r'(?i)\bсистем[ауые]\s*-\s*(\d+)',r'система \1',article.title.casefold())
    tokens=[]
    for word in re.findall(r'[а-яёa-z0-9]+',text):
        word=NORMALIZE.get(word,word)
        if word not in STOP and len(word)>2:
            tokens.append(word)
    return frozenset(tokens)


def _product_marker(article: Article) -> str:
    t=(article.title+' '+article.excerpt).casefold()
    for name,rx in (('linux',r'\blinux\b'),('windows',r'\bwindows\b'),
                    ('android',r'\bandroid\b'),('ios',r'\bios\b'),
                    ('cisco',r'\bcisco\b'),('vmware',r'\bvmware\b')):
        if re.search(rx,t): return name
    return ''


def match_articles(left: Article,right: Article) -> MatchResult:
    a,b=stage(left.title),stage(right.title)
    if a != b and (a or b):
        return MatchResult('different',('different_stage',))
    ac,bc=action(left.title),action(right.title)
    if ac != bc and ac and bc:
        return MatchResult('different',('different_action',))
    ia,ib=bills(left),bills(right)
    if ia and ib and ia.isdisjoint(ib):
        return MatchResult('different',('different_bill_id',))
    ca,cb=cves(left),cves(right)
    if ca and cb and ca.isdisjoint(cb):
        return MatchResult('different',('different_cve',))
    if ca and cb and ca==cb:
        pa,pb=_product_marker(left),_product_marker(right)
        if pa and pb and pa!=pb:
            return MatchResult('different',('different_affected_product',))
    # A publisher may re-use a URL after changing a bill's stage or outcome.
    # Conflict guards must execute before identity checks.
    if left.article_id == right.article_id or left.canonical_url==right.canonical_url:
        return MatchResult('same',('identical_publication',))
    if left.published_at and right.published_at:
        if abs((left.published_at-right.published_at).total_seconds())>72*3600:
            return MatchResult('possible',('distant_publication_dates',))
    if ia and ia==ib:
        if a==b and ac==bc:
            return MatchResult('same',('same_bill_stage_action',))
        return MatchResult('possible',('same_bill_unclear_action',))
    # Keep same-announced-date P2P claims together, without asserting they are
    # legally true. Changing the claimed effective date is a distinct update.
    lhs, rhs = left.title.casefold(), right.title.casefold()
    dates_l, dates_r = set(DATE_IN_TEXT.findall(lhs)), set(DATE_IN_TEXT.findall(rhs))
    same_p2p = all(x.search(lhs) and x.search(rhs)
                   for x in (P2P_BAN, CRYPTO, BAN))
    if same_p2p and dates_l and dates_r:
        if dates_l != dates_r:
            return MatchResult('different',('conflicting_claimed_dates',))
        if a == b and ac == bc:
            return MatchResult('same',('same_p2p_claim_same_date',))
    same_levy = (
        TECH_LEVY.search(lhs) and TECH_LEVY.search(rhs)
        and ELECTRONICS.search(lhs) and ELECTRONICS.search(rhs)
    )
    if same_levy and a == b and ac == bc:
        return MatchResult('same',('same_technology_levy_subject',))
    a_tokens,b_tokens=subject_tokens(left),subject_tokens(right)
    shared=a_tokens & b_tokens
    if min(len(a_tokens),len(b_tokens))<3 or len(shared)<3:
        return MatchResult('different',('too_few_distinctive_tokens',))
    jac=len(shared)/len(a_tokens|b_tokens)
    containment=len(shared)/min(len(a_tokens),len(b_tokens))
    distinctive=shared-GENERIC
    if len(distinctive)>=1 and jac>=.79 and containment>=.85 and ac==bc:
        return MatchResult('same',('high_text_overlap','consistent_action'))
    if len(distinctive)>=1 and jac>=.56 and containment>=.7:
        return MatchResult('possible',('moderate_overlap',))
    return MatchResult('different',('insufficient_overlap',))


def _group_key(article: Article) -> str:
    ids=bills(article)
    if len(ids)==1:
        return 'bill:'+next(iter(ids))+':'+(stage(article.title) or 'unknown')+':'+(action(article.title) or 'unknown')
    cv=cves(article)
    if len(cv)==1:
        return 'cve:'+next(iter(cv))+':'+(_product_marker(article) or 'unspecified')+':'+(action(article.title) or 'unknown')
    return 'event:'+hashlib.sha256(article.article_id.encode()).hexdigest()[:24]


def group_articles(articles: list[Article]) -> list[EventGroup]:
    """Stable input ordering; only explicitly same pair can join a group."""
    groups:list[list[Article]]=[]
    for article in sorted(articles,key=lambda x:(x.published_at or x.fetched_at,x.article_id)):
        found=False
        for group in groups:
            if all(match_articles(article, other).decision=='same' for other in group):
                group.append(article)
                found=True
                break
        if not found:
            groups.append([article])
    result=[]
    for entries in groups:
        entries.sort(key=lambda a:(a.published_at or a.fetched_at,a.article_id))
        main=entries[0]
        result.append(EventGroup(_group_key(main),stage(main.title),
                                 tuple(sorted(a.article_id for a in entries)),
                                 main.title,'', main.published_at, main.excerpt))
    return sorted(result,key=lambda group:group.event_key)
