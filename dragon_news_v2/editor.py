"""Explainable, fully offline editorial relevance and dynamic category priorities."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timedelta
import re
from types import SimpleNamespace
from .evidence import EvidenceAssessment, EvidenceStatus
from .matcher import EventGroup
from direct_news import category as classify_title
from editorial import editorial_score
from editorial_gate import is_publishable

RULES_VERSION='v2.0.0-editorial-2'
# Channel location is contextual metadata, not independent verification.
LOCAL_CUE = re.compile(r'\b(?:улиц[а-я]*|маршрут[а-я]*|район[а-я]*|городск[а-я]*|'
                       r'мкр|микрорайон[а-я]*|школ[а-я]*|дорог[а-я]*|'
                       r'водоснабж[а-я]*|водопровод[а-я]*|электроснабж[а-я]*|'
                       r'липецк[а-я]*)\b',re.I)
OTHER_CITY = re.compile(r'\b(?:москв[а-я]*|воронеж[а-я]*|'
                        r'петербург[а-я]*|екатеринбург[а-я]*|'
                        r'новосибирск[а-я]*|казан[а-я]*)\b',re.I)
PRIORITY = {
    'Липецк и Липецкая область': 4,
    'Законы и правила': 4,
    'Интернет и VPN': 4,
    'Финансы и крипта': 4,
    'Россия — главное': 2,
    'СВО — позиции сторон': 2,
    'Мир и экономика': 2,
    'IT, облака и AI': 2,
    'Инфраструктура и безопасность': 2,
    'Игры на ПК': 1,
}

@dataclass(frozen=True)
class EditorialDecision:
    event_key: str
    include: bool
    category: str
    score: int
    evidence_status: EvidenceStatus
    reason_codes: tuple[str, ...]
    rules_version: str = RULES_VERSION


def evaluate_event(event: EventGroup, evidence: EvidenceAssessment,
                   now: datetime) -> EditorialDecision:
    """No invented facts: evaluate only existing source headline, excerpt and time."""
    if now.tzinfo is None:
        raise ValueError('Digest cutoff must have timezone')
    def reject(reason: str, topic: str='') -> EditorialDecision:
        return EditorialDecision(event.event_key,False,topic,0,evidence.status,
                                 (reason,)+evidence.reason_codes)
    if evidence.status == 'insufficient':
        return reject('insufficient_evidence')
    if evidence.status == 'disputed':
        return reject('disputed_claim_requires_review')
    if event.published_at is None or event.published_at.tzinfo is None:
        return reject('missing_publication_time')
    if not now-timedelta(days=1) <= event.published_at < now:
        return reject('outside_digest_window')
    topic=classify_title(event.title,event.excerpt)
    if (event.category_hint == 'Липецк и Липецкая область'
        and LOCAL_CUE.search(event.title)
        and not OTHER_CITY.search(event.title)):
        topic=classify_title(event.title,event.excerpt,forced=event.category_hint) or topic
    if not topic or topic not in PRIORITY:
        return reject('rejected_not_substantive')
    item=SimpleNamespace(title=event.title,summary=event.excerpt,topic=topic)
    if not is_publishable(item):
        return reject('rejected_not_substantive',topic)
    base=editorial_score(item)
    if base < 2:
        return reject('low_significance',topic)
    weight=PRIORITY[topic]
    score=base+weight
    if score < 5:
        return reject('low_significance',topic)
    reasons=('category:'+topic,'verified_publication_time','significance_score',
             'evidence:'+evidence.status)+evidence.reason_codes
    return EditorialDecision(event.event_key,True,topic,score,evidence.status,reasons)


def rank_events(decisions: list[EditorialDecision], max_items: int=28) -> list[EditorialDecision]:
    """No quotas/no padding. Diversity penalty applies only after 3 per category."""
    limit=max(0,min(30,max_items))
    eligible={d.event_key:d for d in decisions if d.include and d.score>=5}
    selected:list[EditorialDecision]=[]
    category_count:dict[str,int]={}
    while eligible and len(selected)<limit:
        def rank(d: EditorialDecision):
            repeats=max(0,category_count.get(d.category,0)-2)
            adjusted=d.score-3*repeats
            return (adjusted,d.score,-len(d.reason_codes))
        # Stable final tie-break by event_key, independent of input order.
        best=sorted(eligible.values(),key=lambda d:(-rank(d)[0],-rank(d)[1],d.event_key))[0]
        selected.append(best)
        category_count[best.category]=category_count.get(best.category,0)+1
        del eligible[best.event_key]
    return selected
