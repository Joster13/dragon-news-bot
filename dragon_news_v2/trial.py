"""Read-only quality-of-operations report for an isolated seven-day shadow trial.

This is NOT an automated assessment of editorial precision or recall.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

MOSCOW=ZoneInfo("Europe/Moscow")


def require_shadow_only_path(value: str) -> Path:
    """Fail closed if a runner could use a production SQLite path."""
    path=Path(value).expanduser()
    if path.is_symlink():
        raise ValueError("Shadow database must not be a symlink")
    resolved=path.resolve()
    if resolved.name != "dragon_news_shadow.sqlite3":
        raise ValueError("Only dragon_news_shadow.sqlite3 may be used for the shadow trial")
    production=Path(os.getenv("DB_PATH","./data/dragon_news.sqlite3")).expanduser().resolve()
    if resolved==production:
        raise ValueError("Refusing production database path")
    return resolved


def trial_status(db: sqlite3.Connection, now: datetime | None=None) -> dict:
    """Summarize complete calendar days, collector errors, and outstanding review.

    The report is purely informational: offline tests are not manual news
    annotations and never certify 95% precision or 85% recall.
    """
    if now is None:
        now=datetime.now(MOSCOW)
    if now.tzinfo is None:
        raise ValueError("Status time must have a timezone")
    now=now.astimezone(MOSCOW)
    runs=db.execute("SELECT started_at,status,sources_ok,failures FROM collector_runs ORDER BY started_at").fetchall()
    digests=db.execute("SELECT day,status,quality_note FROM digests ORDER BY day").fetchall()
    report={
        "status":"not_started","started_at":None,"checked_at":now.isoformat(),
        "seven_day_window_elapsed":False,
        "collector_runs":len(runs),
        "successful_collections":sum(1 for r in runs if r[1]=="OK"),
        "partial_collections":sum(1 for r in runs if r[1]=="PARTIAL"),
        "failed_collections":sum(1 for r in runs if r[1]=="FAILED"),
        "completed_days":sum(1 for d in digests if d[1]=="READY"),
        "days_seen":len({d[0] for d in digests}),
        "incomplete_days":[d[0] for d in digests if d[1]!="READY"],
        "missing_days":[],
        "ready_for_review":False,
        "quality_review_complete":False,
        "manual_labelled_items":0,
        "precision":None,"recall":None,
    }
    if not runs:
        return report
    first=min(datetime.fromisoformat(r[0]).astimezone(MOSCOW) for r in runs)
    report["started_at"]=first.isoformat()
    elapsed=now>=first+timedelta(days=7)
    report["seven_day_window_elapsed"]=elapsed
    # Only mornings after monitoring actually began count as expected digests.
    first_digest=first.date() if first.hour<9 else first.date()+timedelta(days=1)
    expected=[(first_digest+timedelta(days=i)).isoformat() for i in range(7)]
    actual={day:status for day,status,_ in digests}
    report["missing_days"]=[day for day in expected if day not in actual and now.date().isoformat()>=day]
    operationally_complete=all(actual.get(day)=="READY" for day in expected)
    report["ready_for_review"]=elapsed and operationally_complete
    report["status"]=("ready_for_review" if report["ready_for_review"]
                     else "needs_attention" if elapsed
                     else "collecting")
    return report
