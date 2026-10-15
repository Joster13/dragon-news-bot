"""Opt-in shadow collector child task. Does not instantiate Telegram clients."""
from __future__ import annotations
import asyncio
import logging
import os
from pathlib import Path
from .collector import run_collector_loop
from .db import open_shadow_db

log=logging.getLogger(__name__)


def shadow_enabled() -> bool:
    return os.getenv('V2_SHADOW_ENABLED','false').strip().lower()=='true'


def shadow_db_path() -> str:
    path=os.getenv('V2_DB_PATH','/app/data/dragon_news_shadow.sqlite3')
    prod=os.getenv('DB_PATH','./data/dragon_news.sqlite3')
    if Path(path).expanduser().resolve()==Path(prod).expanduser().resolve():
        raise ValueError('Shadow SQLite cannot share the production DB_PATH')
    if Path(path).name=='dragon_news.sqlite3':
        raise ValueError('Shadow SQLite cannot use the production filename')
    return path


def start_shadow_collector(existing_httpx_client, stop_event: asyncio.Event) -> asyncio.Task:
    """Uses the existing HTTP client without another Telegram poller."""
    path=shadow_db_path()

    async def runner():
        db=open_shadow_db(path)
        try:
            await run_collector_loop(existing_httpx_client,db,stop_event)
        finally:
            db.close()

    task=asyncio.create_task(runner(),name='dragon-news-v2-shadow-collector')

    def report_failure(done: asyncio.Task):
        if not done.cancelled() and done.exception():
            log.error('Shadow collector task failed: %s',type(done.exception()).__name__)

    task.add_done_callback(report_failure)
    return task
