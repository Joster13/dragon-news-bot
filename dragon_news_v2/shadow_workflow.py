"""Schedule and execute shadow-only hourly fetches plus a daily 09:00 snapshot."""
from __future__ import annotations
import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from .collector import collect_once
from .models import CollectorReport
from .scheduler import next_collect_at
from .shadow_pipeline import ShadowBuildResult, build_shadow_digest
from .shadow_schedule import due_shadow_cutoff
from .source_registry import SourceSpec, load_source_specs

log = logging.getLogger(__name__)
MOSCOW = ZoneInfo('Europe/Moscow')


@dataclass(frozen=True)
class ShadowCycle:
    collection: CollectorReport
    digest: ShadowBuildResult | None


async def run_shadow_cycle(client: httpx.AsyncClient, db: sqlite3.Connection,
                           sources: tuple[SourceSpec, ...],
                           now: datetime) -> ShadowCycle:
    """Perform one cycle, writing only to the v2 database. Never sends messages."""
    if now.tzinfo is None:
        raise ValueError('Cycle timestamp must have timezone')
    report = await collect_once(client, db, sources, now)
    today = now.astimezone(MOSCOW).date().isoformat()
    built = db.execute('SELECT 1 FROM digests WHERE day=?', (today,)).fetchone() is not None
    cutoff = due_shadow_cutoff(now, built)
    result = None
    if cutoff is not None:
        # During catchup, include articles fetched before now whose PUBLISHED
        # timestamp is within the normal news window ending at 09:00.
        result = build_shadow_digest(db, cutoff, observed_until=now)
        log.info('V2 shadow snapshot saved: day=%s items=%d status=%s',
                 result.day, result.item_count, result.status)
    return ShadowCycle(report, result)


async def run_shadow_workflow(client: httpx.AsyncClient, db: sqlite3.Connection,
                              stop_event: asyncio.Event) -> None:
    """No Telegram polling, no Rich Messages, no delivery outbox modifications."""
    await run_shadow_cycle(client,db,load_source_specs(),datetime.now(MOSCOW))
    while not stop_event.is_set():
        now=datetime.now(MOSCOW)
        seconds=max(.01,(next_collect_at(now,MOSCOW)-now).total_seconds())
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=seconds)
            return
        except asyncio.TimeoutError:
            try:
                await run_shadow_cycle(client,db,load_source_specs(),datetime.now(MOSCOW))
            except Exception:
                log.exception('V2 shadow collection/editorial cycle failed; will retry next hour')
