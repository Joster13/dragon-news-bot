"""Standalone BotHost entrypoint for Dragon News 2.0 seven-day shadow evaluation.

IMPORTANT: Configure this as the main file of a SEPARATE BotHost project,
not the existing production project. It never accesses Telegram APIs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from urllib.parse import quote

import httpx

from dragon_news_v2.db import open_shadow_db
from dragon_news_v2.shadow_workflow import run_shadow_workflow
from dragon_news_v2.trial import require_shadow_only_path, trial_status

log=logging.getLogger("dragon-news-v2-shadow")


async def main() -> None:
    parser=argparse.ArgumentParser(description="Standalone Dragon News v2 shadow test")
    view=parser.add_mutually_exclusive_group()
    view.add_argument("--status",action="store_true",help="Print counters read-only and exit")
    view.add_argument("--sources",action="store_true",help="Print per-source health read-only")
    view.add_argument("--preview-date",help="Read source-linked items for a YYYY-MM-DD day")
    parser.add_argument("--db",default="/app/data/dragon_news_shadow.sqlite3",
                        help="Dedicated shadow SQLite database file")
    args=parser.parse_args()
    path=require_shadow_only_path(args.db)
    if args.status or args.preview_date or args.sources:
        if not path.is_file():
            raise FileNotFoundError(f"Shadow database not found: {path}")
        uri="file:"+quote(str(path),safe="/")+ "?mode=ro"
        db=sqlite3.connect(uri,uri=True)
        try:
            db.execute("PRAGMA query_only=ON")
            if args.status:
                report=trial_status(db)
            elif args.sources:
                rows=db.execute(
                    """SELECT s.source_id,s.kind,s.url,s.last_error,s.last_success_at,
                              (SELECT COUNT(*) FROM articles a WHERE a.source_id=s.source_id),
                              (SELECT MAX(a.fetched_at) FROM articles a WHERE a.source_id=s.source_id)
                       FROM sources s ORDER BY s.source_id"""
                ).fetchall()
                report={"sources":[{"source_id":row[0],"kind":row[1],"url":row[2],
                                   "last_error":row[3],"last_success_at":row[4],
                                   "article_count":row[5],"last_article_fetched_at":row[6],
                                   "state":"error" if row[3] else ("ok" if row[4] else "unknown")}
                                   for row in rows]}
            else:
                from datetime import date
                day=date.fromisoformat(args.preview_date).isoformat()
                row=db.execute("SELECT digest_id,status,quality_note FROM digests WHERE day=?",(day,)).fetchone()
                if row is None:
                    raise FileNotFoundError(f"No shadow digest for {day}")
                items=[json.loads(r[0]) for r in db.execute(
                    "SELECT rendered_text FROM digest_items WHERE digest_id=? ORDER BY position",(row[0],))]
                report={"day":day,"status":row[1],"quality_note":row[2],"items":items}
            print(json.dumps(report,ensure_ascii=False,indent=2))
        finally:
            db.close()
        return

    # No access to production Storage and no Telegram bot, token or polling.
    db=open_shadow_db(str(path))
    stop=asyncio.Event()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20,connect=12),
                                      follow_redirects=False,
                                      headers={"User-Agent":"DragonNewsShadow/2.0 (open RSS)"}) as client:
            await run_shadow_workflow(client,db,stop)
    finally:
        db.close()


if __name__=="__main__":
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main())
