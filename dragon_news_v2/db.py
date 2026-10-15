"""Transactional, independent shadow database. Never opens the legacy DB."""
from __future__ import annotations
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .models import Article, Source

SCHEMA_V1 = (
    "CREATE TABLE sources (source_id TEXT PRIMARY KEY, kind TEXT NOT NULL, url TEXT NOT NULL UNIQUE, "
    "topic_hints TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1, "
    "last_success_at TEXT, last_error TEXT, last_http_status INTEGER)",
    "CREATE TABLE collector_runs (run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, "
    "finished_at TEXT, status TEXT NOT NULL, sources_ok INTEGER NOT NULL DEFAULT 0, "
    "articles_new INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE articles (article_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id), "
    "canonical_url TEXT NOT NULL, external_id TEXT, published_at TEXT, fetched_at TEXT NOT NULL, "
    "event_time TEXT, title TEXT NOT NULL, excerpt TEXT NOT NULL, raw_fingerprint TEXT NOT NULL, "
    "UNIQUE(source_id, canonical_url))",
    "CREATE INDEX ix_articles_published ON articles(published_at)",
    "CREATE INDEX ix_articles_fetched ON articles(fetched_at)",
    "CREATE TABLE events (event_id TEXT PRIMARY KEY, event_key TEXT NOT NULL, stage TEXT, "
    "headline TEXT NOT NULL, category TEXT, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, "
    "status TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 0, published_in_digest_at TEXT)",
    "CREATE TABLE event_articles (event_id TEXT NOT NULL REFERENCES events(event_id), "
    "article_id TEXT NOT NULL REFERENCES articles(article_id), relation TEXT NOT NULL, "
    "PRIMARY KEY(event_id,article_id))",
    "CREATE TABLE editorial_decisions (decision_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(event_id), "
    "rule_version TEXT NOT NULL, decision TEXT NOT NULL, score REAL NOT NULL, "
    "reason_codes TEXT NOT NULL, checked_at TEXT NOT NULL)",
    "CREATE TABLE digests (digest_id TEXT PRIMARY KEY, day TEXT NOT NULL UNIQUE, cutoff_at TEXT NOT NULL, "
    "built_at TEXT NOT NULL, build_version TEXT NOT NULL, status TEXT NOT NULL, quality_note TEXT)",
    "CREATE TABLE digest_items (digest_id TEXT NOT NULL REFERENCES digests(digest_id), "
    "event_id TEXT NOT NULL REFERENCES events(event_id), position INTEGER NOT NULL, "
    "rendered_text TEXT NOT NULL, PRIMARY KEY(digest_id,event_id), UNIQUE(digest_id,position))",
    "CREATE TABLE delivery_outbox (part_id TEXT PRIMARY KEY, digest_id TEXT NOT NULL REFERENCES digests(digest_id), "
    "part_index INTEGER NOT NULL, payload_hash TEXT NOT NULL, state TEXT NOT NULL, "
    "attempts INTEGER NOT NULL DEFAULT 0, telegram_message_id INTEGER, last_error TEXT, "
    "updated_at TEXT NOT NULL, UNIQUE(digest_id, part_index))",
)
SCHEMA_CHECKSUM = hashlib.sha256('\n'.join(SCHEMA_V1).encode()).hexdigest()


def open_shadow_db(path: str) -> sqlite3.Connection:
    """Create/migrate only a dedicated v2 SQLite database; reject legacy paths."""
    p = Path(path).expanduser().resolve()
    if p.name == 'dragon_news.sqlite3':
        raise ValueError('Refusing to open the production SQLite database')
    p.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(p), timeout=15)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        legacy = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('seen','deliveries','event_history')"
        ).fetchone()
        if legacy:
            raise ValueError('Refusing shadow migrations on a legacy database')
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations '
                   '(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, checksum TEXT NOT NULL)')
        existing = db.execute('SELECT checksum FROM schema_migrations WHERE version=1').fetchone()
        if existing and existing[0] != SCHEMA_CHECKSUM:
            raise ValueError('Shadow SQLite migration checksum mismatch')
        if not existing:
            for statement in SCHEMA_V1:
                db.execute(statement)
            db.execute('INSERT INTO schema_migrations (version,applied_at,checksum) VALUES (?,?,?)',
                       (1, datetime.now(timezone.utc).isoformat(), SCHEMA_CHECKSUM))
        db.commit()
        return db
    except BaseException:
        db.rollback()
        db.close()
        raise


def register_source(db: sqlite3.Connection, source: Source) -> None:
    with db:
        db.execute('INSERT INTO sources (source_id,kind,url,enabled) VALUES (?,?,?,?) '
                   'ON CONFLICT(source_id) DO UPDATE SET kind=excluded.kind, '
                   'url=excluded.url, enabled=excluded.enabled',
                   (source.source_id, source.kind, source.url, int(source.enabled)))


def upsert_article(db: sqlite3.Connection, article: Article) -> bool:
    if article.fetched_at.tzinfo is None:
        raise ValueError('fetched_at must be timezone aware')
    with db:
        result = db.execute(
            'INSERT OR IGNORE INTO articles '
            '(article_id,source_id,canonical_url,title,excerpt,published_at,fetched_at,event_time,raw_fingerprint) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            (article.article_id, article.source_id, article.canonical_url, article.title,
             article.excerpt, article.published_at.isoformat() if article.published_at else None,
             article.fetched_at.isoformat(), article.event_time.isoformat() if article.event_time else None,
             article.fingerprint),
        )
        if result.rowcount == 0 and not db.execute('SELECT 1 FROM sources WHERE source_id=?',
                                                  (article.source_id,)).fetchone():
            raise sqlite3.IntegrityError('Unknown source_id')
        return result.rowcount == 1


def mark_source_result(db: sqlite3.Connection, source_id: str, succeeded: bool,
                       fetched_at: datetime, error_code: str | None) -> None:
    with db:
        if succeeded:
            result = db.execute('UPDATE sources SET last_success_at=?,last_error=NULL,last_http_status=NULL '
                                'WHERE source_id=?', (fetched_at.isoformat(), source_id))
        else:
            result = db.execute('UPDATE sources SET last_error=? WHERE source_id=?', (error_code,source_id))
        if result.rowcount != 1:
            raise ValueError('Unknown source_id')
