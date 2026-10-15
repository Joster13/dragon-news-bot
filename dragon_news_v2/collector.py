"""Concurrent bounded hourly collection; shadow DB only, no Telegram polling."""
from __future__ import annotations
import asyncio
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import httpx
from .adapters import parse_feed, validated_source_url
from .db import register_source, mark_source_result, upsert_article
from .models import CollectorReport, Source
from .scheduler import next_collect_at
from .source_registry import SourceSpec, load_source_specs

log=logging.getLogger(__name__)
_COLLECTOR_LOCK=asyncio.Lock()


async def collect_once(client: httpx.AsyncClient, db: sqlite3.Connection,
                       sources: tuple[SourceSpec,...], now: datetime) -> CollectorReport:
    """One idempotent cycle. Never follows redirects or reads article URLs."""
    async with _COLLECTOR_LOCK:
        run_id=str(uuid.uuid4())
        sem=asyncio.Semaphore(5)
        with db:
            db.execute('INSERT INTO collector_runs(run_id,started_at,status) VALUES (?,?,?)',
                       (run_id,now.isoformat(),'RUNNING'))
        for s in sources:
            register_source(db,Source(s.source_id,s.kind,s.url))

        async def fetch(s:SourceSpec):
            async with sem:
                host=urlsplit(s.url).hostname
                if not host or not validated_source_url(s.url,frozenset({host})):
                    return s,[], 'INVALID_SOURCE_URL'
                try:
                    response=await client.get(s.url,timeout=12,follow_redirects=False,
                                              headers={'Accept':'application/rss+xml, application/xml, text/html'})
                    if response.status_code!=200:
                        return s,[],f'HTTP_{response.status_code}'
                    if len(response.content)>s.max_bytes:
                        return s,[],'TOO_LARGE'
                    return s,parse_feed(s,response.content,now),None
                except (httpx.HTTPError,ValueError,UnicodeError) as exc:
                    return s,[],type(exc).__name__

        results=await asyncio.gather(*(fetch(s) for s in sources))
        ok=failed=inserted=0
        for source,articles,error in results:
            if error:
                failed+=1
                mark_source_result(db,source.source_id,False,now,error)
                continue
            ok+=1
            mark_source_result(db,source.source_id,True,now,None)
            for a in articles:
                if upsert_article(db,a):
                    inserted+=1
        with db:
            db.execute('UPDATE collector_runs SET finished_at=?,status=?,sources_ok=?,articles_new=?,failures=? WHERE run_id=?',
                       (datetime.now(timezone.utc).isoformat(),
                        'OK' if failed==0 else ('PARTIAL' if ok else 'FAILED'),ok,inserted,failed,run_id))
        log.info('V2 shadow collector: ok=%s failures=%s added=%s',ok,failed,inserted)
        return CollectorReport(run_id,ok,failed,inserted)


async def run_collector_loop(client: httpx.AsyncClient, db: sqlite3.Connection,
                             stop_event: asyncio.Event) -> None:
    """Opt-in loop. Runs immediately after startup and then every Moscow hour."""
    tz=ZoneInfo('Europe/Moscow')
    await collect_once(client,db,load_source_specs(),datetime.now(tz))
    while not stop_event.is_set():
        now=datetime.now(tz)
        wait=max(0.01,(next_collect_at(now,tz)-now).total_seconds())
        try:
            await asyncio.wait_for(stop_event.wait(),timeout=wait)
            break
        except asyncio.TimeoutError:
            await collect_once(client,db,load_source_specs(),datetime.now(tz))
