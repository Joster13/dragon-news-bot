"""Immutable factual digest snapshots. No model-generated explanations."""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass,asdict
from datetime import date, datetime
from urllib.parse import urlsplit
from .models import Article
from .matcher import EventGroup
from .editor import EditorialDecision

@dataclass(frozen=True)
class DigestItem:
    event_key: str
    category: str
    headline: str
    facts: str
    source_urls: tuple[str, ...]
    evidence_status: str

@dataclass(frozen=True)
class DigestSnapshot:
    day: date
    cutoff_at: datetime
    items: tuple[DigestItem,...]
    content_hash: str
    quality_note: str


def _safe_source(url: str) -> bool:
    try:
        p=urlsplit(url)
        return p.scheme=='https' and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False


def build_digest(day: date, decisions: list[EditorialDecision],
                 events: dict[str,EventGroup], articles: dict[str,Article],
                 cutoff_at: datetime) -> DigestSnapshot:
    if cutoff_at.tzinfo is None:
        raise ValueError('Digest cutoff must be timezone aware')
    items=[]
    for decision in decisions:
        if not decision.include:
            continue
        event=events[decision.event_key]
        linked=[articles[x] for x in event.article_ids]
        if not linked:
            raise ValueError('An included event must have source articles')
        urls=tuple(dict.fromkeys(article.canonical_url for article in linked))
        if not urls or any(not _safe_source(url) for url in urls):
            raise ValueError('Digest item contains an unsafe or missing source URL')
        # Prefer one richest primary-source description, not a synthetic fusion.
        chosen=sorted(linked,key=lambda a:(-len(a.excerpt),a.article_id))[0]
        items.append(DigestItem(event.event_key,decision.category,event.title,
                                chosen.excerpt, urls,decision.evidence_status))
    if len(items)>30:
        raise ValueError('Digest must contain no more than 30 news events')
    items_tuple=tuple(items)
    payload={
        'day':day.isoformat(),'cutoff_at':cutoff_at.isoformat(),
        'items':[asdict(item) for item in items_tuple],
    }
    digest=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,
                                     separators=(',',':')).encode()).hexdigest()
    quality=('Качественных событий меньше 20; дополнительные публикации не добавлялись'
             if len(items_tuple)<20 else '')
    return DigestSnapshot(day,cutoff_at,items_tuple,digest,quality)
