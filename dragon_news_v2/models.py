"""Immutable types exchanged between v2 collector and storage."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Article:
    article_id: str
    source_id: str
    canonical_url: str
    title: str
    excerpt: str
    published_at: datetime | None
    fetched_at: datetime
    event_time: datetime | None
    fingerprint: str


@dataclass(frozen=True)
class Source:
    source_id: str
    kind: str
    url: str
    enabled: bool = True


@dataclass(frozen=True)
class CollectorReport:
    run_id: str
    ok_count: int
    failed_count: int
    inserted_count: int
