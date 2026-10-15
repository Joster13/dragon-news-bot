"""Evidence provenance assessment. Distinct news sites are not necessarily distinct roots."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit
from .matcher import EventGroup
from .models import Article
from .source_registry import load_source_specs

EvidenceStatus = Literal['official_statement','multi_independent','single_attributed','disputed','insufficient']

@dataclass(frozen=True)
class EvidenceAssessment:
    status: EvidenceStatus
    roots: tuple[str, ...]
    reason_codes: tuple[str, ...]

TRUSTED_SOURCES = frozenset(s.source_id for s in load_source_specs())
OFFICIAL_HOSTS = frozenset({
    'cbr.ru','www.cbr.ru','government.ru','www.government.ru',
    'publication.pravo.gov.ru','duma.gov.ru','www.duma.gov.ru',
    'rkn.gov.ru','www.rkn.gov.ru','minfin.gov.ru','www.minfin.gov.ru',
})
OFFICIAL_IDS = frozenset({'cbr','government','pravo','duma','rkn','minfin'})
CONTRADICTION = re.compile(r'\b(?:опроверг\w*|отрица\w*|не\s+подтверд\w*|не\s+было)\b',re.I)
CONFIRMATION = re.compile(r'\b(?:подтверд\w*|заявил\w*\s+о\s+контрол\w*|сообщил\w*\s+о\s+контрол\w*)\b',re.I)


def _traceable(article: Article) -> bool:
    try:
        p=urlsplit(article.canonical_url)
        return p.scheme=='https' and bool(p.hostname) and bool(article.title.strip())
    except ValueError:
        return False


def _official(article: Article) -> bool:
    try:
        return article.source_id in OFFICIAL_IDS and urlsplit(article.canonical_url).hostname in OFFICIAL_HOSTS
    except ValueError:
        return False


def assess_evidence(event: EventGroup, articles: dict[str,Article],
                    origin_map: dict[str,str]) -> EvidenceAssessment:
    """Require explicitly established origin roots to claim independent corroboration."""
    if not event.article_ids or any(aid not in articles for aid in event.article_ids):
        return EvidenceAssessment('insufficient',(),('missing_articles',))
    items=[articles[aid] for aid in event.article_ids]
    if any(not _traceable(item) for item in items):
        return EvidenceAssessment('insufficient',(),('no_traceable_https_source',))
    if not all(a.source_id in TRUSTED_SOURCES or _official(a) for a in items):
        return EvidenceAssessment('insufficient',(),('unrecognized_source',))
    orig=tuple(sorted(set(v.strip() for a in items
                          if (v:=origin_map.get(a.article_id)) and v.strip())))
    origins_complete=all(origin_map.get(a.article_id,'').strip() for a in items)
    roots=orig if orig else ('unverified',)
    texts=[a.title+' '+a.excerpt for a in items]
    neg=any(CONTRADICTION.search(text) for text in texts)
    pos=any(CONFIRMATION.search(text) for text in texts)
    if neg and pos:
        return EvidenceAssessment('disputed',roots,('contradictory_source_claims',))
    if any(_official(a) for a in items):
        return EvidenceAssessment('official_statement',roots,('official_primary_source','not_independent_fact_verification'))
    if not origins_complete:
        return EvidenceAssessment('single_attributed',roots,('origin_unverified',))
    if len(orig)>=2:
        return EvidenceAssessment('multi_independent',roots,('two_distinct_origin_roots',))
    return EvidenceAssessment('single_attributed',roots,('one_information_origin',))
