"""Build DB-only 09:00 shadow digests from the hourly collector's SQLite articles.

No Telegram API calls, no legacy Storage imports, no writes to the production DB.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .builder import build_digest
from .editor import RULES_VERSION, evaluate_event, rank_events
from .evidence import assess_evidence
from .legacy_bridge import render_v2_digest
from .matcher import group_articles
from .models import Article
from .source_registry import load_source_specs

MOSCOW = ZoneInfo("Europe/Moscow")
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS shadow_snapshots (
    day TEXT PRIMARY KEY REFERENCES digests(day),
    digest_id TEXT NOT NULL UNIQUE REFERENCES digests(digest_id),
    content_hash TEXT NOT NULL,
    item_count INTEGER NOT NULL,
    rich_html TEXT NOT NULL,
    plain_chunks_json TEXT NOT NULL,
    quality_note TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
SCHEMA_CHECKSUM = hashlib.sha256(SCHEMA_SQL.encode()).hexdigest()


@dataclass(frozen=True)
class ShadowBuildResult:
    day: str
    digest_id: str
    item_count: int
    content_hash: str
    created: bool
    status: str


def _ensure_schema(db: sqlite3.Connection) -> None:
    """Additive migration only in the v2 shadow database."""
    with db:
        row = db.execute("SELECT checksum FROM schema_migrations WHERE version=2").fetchone()
        if row and row[0] != SCHEMA_CHECKSUM:
            raise ValueError("Shadow snapshot schema checksum mismatch")
        if not row:
            db.execute(SCHEMA_SQL)
            db.execute(
                "INSERT INTO schema_migrations(version,applied_at,checksum) VALUES (?,?,?)",
                (2, datetime.now(MOSCOW).isoformat(), SCHEMA_CHECKSUM),
            )


def _stored_result(db: sqlite3.Connection, day: str) -> ShadowBuildResult | None:
    row = db.execute(
        """SELECT s.day,s.digest_id,s.item_count,s.content_hash,d.status
           FROM shadow_snapshots s JOIN digests d ON d.digest_id=s.digest_id
           WHERE s.day=?""",
        (day,),
    ).fetchone()
    return ShadowBuildResult(row[0], row[1], row[2], row[3], False, row[4]) if row else None


def _load_candidate_articles(db: sqlite3.Connection, cutoff: datetime,
                             observed_until: datetime) -> dict[str, Article]:
    # Three days of context allows a syndicated reprint to match an old event.
    # SQLite julianday normalizes mixed timezone offsets, unlike string comparison.
    start = (cutoff - timedelta(hours=72)).isoformat()
    end = cutoff.isoformat()
    observed = observed_until.isoformat()
    rows = db.execute(
        """SELECT article_id,source_id,canonical_url,title,excerpt,
                  published_at,fetched_at,event_time,raw_fingerprint
           FROM articles
           WHERE julianday(fetched_at) <= julianday(?)
             AND ((julianday(published_at) >= julianday(?)
                   AND julianday(published_at) < julianday(?))
                  OR (published_at IS NULL
                      AND julianday(fetched_at) >= julianday(?)))
           ORDER BY julianday(COALESCE(published_at,fetched_at)),article_id
           LIMIT 2500""",
        (observed, start, end, start),
    ).fetchall()
    def parse(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None
    return {
        row[0]: Article(row[0], row[1], row[2], row[3], row[4],
                        parse(row[5]), parse(row[6]), parse(row[7]), row[8])
        for row in rows
    }


def _event_id(event_key: str) -> str:
    return hashlib.sha256(event_key.encode()).hexdigest()


def _coverage_note(db: sqlite3.Connection, cutoff: datetime, observed: datetime) -> tuple[str, bool]:
    start = (cutoff - timedelta(days=1)).isoformat()
    row = db.execute(
        "SELECT count(*),coalesce(max(sources_ok),0),coalesce(sum(failures),0) "
        "FROM collector_runs WHERE started_at >= ? AND started_at <= ?",
        (start, observed.isoformat()),
    ).fetchone()
    runs, best_sources, failures = row
    if not runs or not best_sources:
        return ("Недостаточно данных об успешном сборе источников за сутки", False)
    if failures:
        return (f"Ограниченный охват: за сутки обнаружены ошибки сбора ({failures})", True)
    return ("", True)


def build_shadow_digest(db: sqlite3.Connection, cutoff_at: datetime,
                        max_items: int=28, observed_until: datetime | None=None,
                        retry_incomplete: bool=False) -> ShadowBuildResult:
    """Persist an immutable daily preview and editorial audit transactionally."""
    if cutoff_at.tzinfo is None:
        raise ValueError("Timezone-aware digest cutoff required")
    cutoff = cutoff_at.astimezone(MOSCOW)
    if (cutoff.hour, cutoff.minute, cutoff.second, cutoff.microsecond) != (9, 0, 0, 0):
        raise ValueError("Daily shadow cutoff must be 09:00 Moscow")
    day = cutoff.date().isoformat()
    _ensure_schema(db)
    cached = _stored_result(db, day)
    if cached and not (retry_incomplete and cached.status == "INCOMPLETE"):
        return cached

    observed = observed_until or cutoff
    if observed.tzinfo is None or observed < cutoff:
        raise ValueError("Observed timestamp must follow the cutoff and have a timezone")
    articles = _load_candidate_articles(db, cutoff, observed)
    regional_sources = {s.source_id for s in load_source_specs()
                        if 'Липецк и Липецкая область' in s.topics}
    grouped = [
        replace(g, category_hint='Липецк и Липецкая область')
        if any(articles[aid].source_id in regional_sources for aid in g.article_ids)
        else g
        for g in group_articles(list(articles.values()))
    ]
    groups = {g.event_key: g for g in grouped}
    # Unknown publication origin never counts as multiple independent reports.
    evidence = {g.event_key: assess_evidence(g, articles, {}) for g in grouped}
    decisions = [evaluate_event(g, evidence[g.event_key], cutoff) for g in grouped]
    chosen = rank_events(decisions, max_items)
    snapshot = build_digest(cutoff.date(), chosen, groups, articles, cutoff)
    rich, plain = render_v2_digest(snapshot)
    coverage_note, coverage_good = _coverage_note(db, cutoff, observed)
    note = "; ".join(x for x in (snapshot.quality_note, coverage_note) if x)
    status = "READY" if coverage_good else "INCOMPLETE"
    digest_id = "shadow:" + day
    # Compute and validate everything above BEFORE beginning any data modification.
    with db:
        for g in grouped:
            decision = next(d for d in decisions if d.event_key == g.event_key)
            ev_id = _event_id(g.event_key)
            linked = [articles[aid] for aid in g.article_ids]
            fetched_times = [a.fetched_at for a in linked]
            first_seen = min(fetched_times).isoformat()
            last_seen = max(fetched_times).isoformat()
            db.execute(
                """INSERT INTO events(event_id,event_key,stage,headline,category,
                     first_seen_at,last_seen_at,status,confidence,published_in_digest_at)
                     VALUES (?,?,?,?,?,?,?,?,?,NULL)
                     ON CONFLICT(event_id) DO UPDATE SET
                     last_seen_at=excluded.last_seen_at,
                     category=excluded.category,status=excluded.status""",
                (ev_id, g.event_key, g.stage, g.title, decision.category,
                 first_seen, last_seen, evidence[g.event_key].status, 0.0),
            )
            for aid in g.article_ids:
                db.execute(
                    "INSERT OR IGNORE INTO event_articles(event_id,article_id,relation) "
                    "VALUES (?,?,?)", (ev_id, aid, "same_event"),
                )
            dec_id = hashlib.sha256((day + "\0" + g.event_key + "\0" +
                                     RULES_VERSION).encode()).hexdigest()
            db.execute(
                """INSERT INTO editorial_decisions(
                   decision_id,event_id,rule_version,decision,score,reason_codes,checked_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(decision_id) DO UPDATE SET decision=excluded.decision,
                     score=excluded.score, reason_codes=excluded.reason_codes,
                     checked_at=excluded.checked_at""",
                (dec_id, ev_id, RULES_VERSION, "include" if decision.include else "exclude",
                 decision.score, json.dumps(decision.reason_codes, ensure_ascii=False),
                 cutoff.isoformat()),
            )

        db.execute(
            """INSERT INTO digests(digest_id,day,cutoff_at,built_at,build_version,status,quality_note)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(day) DO UPDATE SET built_at=excluded.built_at,
                 status=excluded.status,quality_note=excluded.quality_note""",
            (digest_id, day, cutoff.isoformat(), datetime.now(MOSCOW).isoformat(),
             RULES_VERSION, status, note),
        )
        if cached:
            db.execute("DELETE FROM digest_items WHERE digest_id=?", (digest_id,))
        for position, item in enumerate(snapshot.items, 1):
            eid = _event_id(item.event_key)
            db.execute(
                "INSERT INTO digest_items(digest_id,event_id,position,rendered_text) "
                "VALUES (?,?,?,?)",
                (digest_id, eid, position, json.dumps(asdict(item), ensure_ascii=False)),
            )
            db.execute(
                "UPDATE events SET published_in_digest_at=? WHERE event_id=?",
                (cutoff.isoformat(), eid),
            )
        db.execute(
            """INSERT INTO shadow_snapshots(day,digest_id,content_hash,item_count,
                rich_html,plain_chunks_json,quality_note,created_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(day) DO UPDATE SET content_hash=excluded.content_hash,
                  item_count=excluded.item_count,rich_html=excluded.rich_html,
                  plain_chunks_json=excluded.plain_chunks_json,
                  quality_note=excluded.quality_note,created_at=excluded.created_at""",
            (day, digest_id, snapshot.content_hash, len(snapshot.items), rich,
             json.dumps(plain, ensure_ascii=False), note, datetime.now(MOSCOW).isoformat()),
        )

    return ShadowBuildResult(day, digest_id, len(snapshot.items), snapshot.content_hash,
                             True, status)


def get_shadow_digest(db: sqlite3.Connection, day: str) -> dict | None:
    _ensure_schema(db)
    row = db.execute(
        """SELECT s.day,s.digest_id,s.content_hash,s.item_count,
                  s.rich_html,s.plain_chunks_json,s.quality_note,d.status
           FROM shadow_snapshots s JOIN digests d ON d.digest_id=s.digest_id
           WHERE s.day=?""",
        (day,),
    ).fetchone()
    if row is None:
        return None
    return {
        "day":row[0], "digest_id":row[1], "content_hash":row[2],
        "item_count":row[3], "rich_html":row[4],
        "plain_chunks":json.loads(row[5]), "quality_note":row[6],
        "status":row[7], "sent_to_telegram":False,
    }
