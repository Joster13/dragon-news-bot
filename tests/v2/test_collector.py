"""Offline hourly collector tests with httpx.MockTransport."""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zoneinfo import ZoneInfo
import httpx
from dragon_news_v2.collector import collect_once
from dragon_news_v2.db import open_shadow_db
from dragon_news_v2.source_registry import SourceSpec
from dragon_news_v2.scheduler import next_collect_at

NOW=datetime(2026,10,15,12,17,tzinfo=timezone.utc)
RSS=b'<rss><channel><item><title>Policy decision</title><link>https://a.test/story</link><pubDate>Thu, 15 Oct 2026 12:00:00 +0000</pubDate></item></channel></rss>'
SOURCES=(SourceSpec('a','https://a.test/feed','rss',()),SourceSpec('b','https://b.test/feed','rss',()))


class CollectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_failure_does_not_block(self):
        def serve(req): return httpx.Response(200,content=RSS) if req.url.host=='a.test' else httpx.Response(500)
        with TemporaryDirectory() as d:
            db=open_shadow_db(str(Path(d)/'shadow.sqlite3'))
            async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
                result=await collect_once(client,db,SOURCES,NOW)
            self.assertEqual((result.ok_count,result.failed_count,result.inserted_count),(1,1,1))
            self.assertEqual(db.execute('SELECT count(*) FROM articles').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT last_error FROM sources WHERE source_id='b'").fetchone()[0],'HTTP_500')
            db.close()

    async def test_restart_idempotence(self):
        with TemporaryDirectory() as d:
            path=str(Path(d)/'shadow.sqlite3')
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=RSS))) as client:
                db=open_shadow_db(path)
                first=await collect_once(client,db,SOURCES[:1],NOW)
                db.close()
                db=open_shadow_db(path)
                second=await collect_once(client,db,SOURCES[:1],NOW)
                self.assertEqual(first.inserted_count,1)
                self.assertEqual(second.inserted_count,0)
                self.assertEqual(db.execute('SELECT count(*) FROM articles').fetchone()[0],1)
                db.close()

    async def test_rate_limit_status(self):
        with TemporaryDirectory() as d:
            db=open_shadow_db(str(Path(d)/'shadow.sqlite3'))
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(429,headers={'Retry-After':'60'}))) as client:
                report=await collect_once(client,db,SOURCES[:1],NOW)
            self.assertEqual(report.failed_count,1)
            self.assertEqual(db.execute("SELECT last_error FROM sources WHERE source_id='a'").fetchone()[0],'HTTP_429')
            db.close()

    async def test_last_success_only_on_ok(self):
        status=iter([200,500])
        def serve(req):
            code=next(status)
            return httpx.Response(code,content=RSS if code==200 else b'error')
        with TemporaryDirectory() as d:
            db=open_shadow_db(str(Path(d)/'shadow.sqlite3'))
            async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
                await collect_once(client,db,SOURCES[:1],NOW)
                await collect_once(client,db,SOURCES[:1],NOW+timedelta(hours=1))
            self.assertEqual(db.execute("SELECT last_success_at FROM sources WHERE source_id='a'").fetchone()[0],NOW.isoformat())
            db.close()

    async def test_parallel_run_is_guarded(self):
        async def serve(req):
            await asyncio.sleep(.015)
            return httpx.Response(200,content=RSS)
        with TemporaryDirectory() as d:
            db=open_shadow_db(str(Path(d)/'shadow.sqlite3'))
            async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
                results=await asyncio.gather(collect_once(client,db,SOURCES[:1],NOW),collect_once(client,db,SOURCES[:1],NOW))
            self.assertEqual(sum(r.inserted_count for r in results),1)
            self.assertEqual(db.execute('SELECT count(*) FROM articles').fetchone()[0],1)
            db.close()

    async def test_empty_feed_counts_as_healthy(self):
        with TemporaryDirectory() as d:
            db=open_shadow_db(str(Path(d)/'shadow.sqlite3'))
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=b'<rss><channel></channel></rss>'))) as client:
                report=await collect_once(client,db,SOURCES[:1],NOW)
            self.assertEqual((report.ok_count,report.inserted_count),(1,0))
            db.close()

    def test_next_hour_timezone(self):
        tz=ZoneInfo('Europe/Moscow')
        next_at=next_collect_at(NOW,tz)
        self.assertEqual(next_at.hour,16)
        self.assertEqual(next_at.minute,0)
        self.assertGreater(next_at,NOW.astimezone(tz))

if __name__=='__main__': unittest.main()
