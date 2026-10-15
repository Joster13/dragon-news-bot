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
    parser.add_argument("--status",action="store_true",help="Print counters read-only and exit")
    parser.add_argument("--db",default="/app/data/dragon_news_shadow.sqlite3",
                        help="Dedicated shadow SQLite database file")
    args=parser.parse_args()
    path=require_shadow_only_path(args.db)
    if args.status:
        if not path.is_file():
            raise FileNotFoundError(f"Shadow database not found: {path}")
        uri="file:"+quote(str(path),safe="/")+ "?mode=ro"
        db=sqlite3.connect(uri,uri=True)
        try:
            db.execute("PRAGMA query_only=ON")
            report=trial_status(db)
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
