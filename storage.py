import os
import sqlite3
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace


class Storage:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, timestamp TEXT NOT NULL)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS deliveries (day TEXT PRIMARY KEY, at TEXT NOT NULL, markdown TEXT NOT NULL)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS event_history (topic TEXT NOT NULL, title TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY(topic, title))")
        self.conn.commit()

    def seen(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT key FROM seen")}

    def has_delivered(self, date: str) -> bool:
        return self.conn.execute("SELECT 1 FROM deliveries WHERE day=?", (date,)).fetchone() is not None

    def record(self, date: str, markdown: str, keys: list[str], articles=None):
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO deliveries VALUES (?,?,?)", (date, now, markdown))
            self.conn.executemany("INSERT OR IGNORE INTO seen VALUES (?,?)", [(k, now) for k in keys])
            if articles:
                self.conn.executemany(
                    "INSERT OR REPLACE INTO event_history(topic, title, at) VALUES (?, ?, ?)",
                    [(x.topic, x.title, now) for x in articles])
                cutoff = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
                self.conn.execute("DELETE FROM event_history WHERE at < ?", (cutoff,))

    def recent_events(self, days: int = 3):
        """Used to suppress the same event from a different publisher tomorrow."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            "SELECT topic, title FROM event_history WHERE at >= ?", (cutoff,)).fetchall()
        return [SimpleNamespace(topic=topic, title=title) for topic, title in rows]

    def last(self):
        return self.conn.execute("SELECT day,at,markdown FROM deliveries ORDER BY day DESC LIMIT 1").fetchone()

    def setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def put_setting(self, key: str, value: str):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))
