"""Test shadow SQLite isolation, migrations and idempotent persistence."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from dragon_news_v2.models import Article, Source
from dragon_news_v2.db import open_shadow_db, upsert_article, register_source, mark_source_result

T = datetime(2026, 10, 15, 9, tzinfo=timezone.utc)


def article():
    return Article(
        article_id="news:123", source_id="rss:test", canonical_url="https://example.org/news/123",
        title="Новое правило действует с октября", excerpt="Подробности публикации.",
        published_at=T, fetched_at=T, event_time=None, fingerprint="fixture-123",
    )


class ShadowDatabaseTests(unittest.TestCase):
    def test_shadow_db_idempotent_and_legacy_untouched(self):
        with TemporaryDirectory() as folder:
            legacy_path = Path(folder) / "dragon_news.sqlite3"
            original = sqlite3.connect(legacy_path)
            original.executescript("""
            CREATE TABLE seen(key TEXT PRIMARY KEY, timestamp TEXT NOT NULL);
            CREATE TABLE deliveries(day TEXT PRIMARY KEY, at TEXT NOT NULL, markdown TEXT NOT NULL);
            CREATE TABLE event_history(topic TEXT NOT NULL, title TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY(topic,title));
            INSERT INTO seen VALUES('legacy-event','2026-10-15');
            INSERT INTO deliveries VALUES('2026-10-15','2026-10-15','original');
            INSERT INTO event_history VALUES('Новости','legacy-event','2026-10-15');
            """)
            original.commit()
            original.close()
            original_bytes = legacy_path.read_bytes()
            shadow_path = Path(folder) / "dragon_news_shadow.sqlite3"
            db = open_shadow_db(str(shadow_path))
            register_source(db, Source("rss:test", "rss", "https://example.org/feed"))
            self.assertTrue(upsert_article(db, article()))
            self.assertFalse(upsert_article(db, article()))
            self.assertEqual(db.execute("SELECT count(*) FROM articles").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            db.close()
            db = open_shadow_db(str(shadow_path))
            self.assertEqual(db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 1)
            self.assertFalse(upsert_article(db, article()))
            db.close()
            self.assertEqual(legacy_path.read_bytes(), original_bytes)
            inspection = sqlite3.connect(shadow_path)
            try:
                self.assertNotIn("seen", [r[0] for r in inspection.execute("SELECT name FROM sqlite_master")])
            finally:
                inspection.close()

    def test_rejects_existing_production_database_path(self):
        with TemporaryDirectory() as folder:
            prod = Path(folder) / "dragon_news.sqlite3"
            sqlite3.connect(prod).close()
            with self.assertRaises(ValueError):
                open_shadow_db(str(prod))

    def test_source_failure_does_not_erase_last_success(self):
        with TemporaryDirectory() as folder:
            db = open_shadow_db(str(Path(folder) / "dragon_news_shadow.sqlite3"))
            register_source(db, Source("rss:test", "rss", "https://example.org/feed"))
            mark_source_result(db, "rss:test", True, T, None)
            mark_source_result(db, "rss:test", False, T.replace(hour=10), "HTTP_429")
            row = db.execute("SELECT last_success_at,last_error FROM sources WHERE source_id='rss:test'").fetchone()
            self.assertEqual(row[0], T.isoformat())
            self.assertEqual(row[1], "HTTP_429")
            db.close()

    def test_foreign_key_rejects_articles_from_unknown_sources(self):
        with TemporaryDirectory() as folder:
            db = open_shadow_db(str(Path(folder) / "dragon_news_shadow.sqlite3"))
            with self.assertRaises(sqlite3.IntegrityError):
                upsert_article(db, article())
            db.close()

    def test_migration_checksum_cannot_change_silently(self):
        with TemporaryDirectory() as folder:
            path = str(Path(folder) / "dragon_news_shadow.sqlite3")
            db = open_shadow_db(path)
            db.execute("UPDATE schema_migrations SET checksum='tampered' WHERE version=1")
            db.commit()
            db.close()
            with self.assertRaises(ValueError):
                open_shadow_db(path)


if __name__ == '__main__':
    unittest.main()
