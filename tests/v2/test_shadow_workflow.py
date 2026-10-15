"""Collector-to-editor shadow-only orchestration tests."""
import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from dragon_news_v2.db import open_shadow_db
from dragon_news_v2.shadow_pipeline import get_shadow_digest
from dragon_news_v2.shadow_workflow import run_shadow_cycle
from dragon_news_v2.source_registry import SourceSpec

MOSCOW=ZoneInfo("Europe/Moscow")
DAY=datetime(2026,10,15,9,tzinfo=MOSCOW)
SOURCE=SourceSpec("tass","https://tass.ru/rss/v2.xml","rss",())
RSS=("""
<rss><channel><item>
<title>Госдума приняла законопроект 123456-8 о новых правилах в первом чтении</title>
<link>https://tass.ru/2026/10/15/001</link>
<pubDate>Thu, 15 Oct 2026 08:30:00 +0300</pubDate>
<description>Подробности по первому чтению законопроекта и условия изменения.</description>
</item></channel></rss>
""").encode("utf-8")


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.db=open_shadow_db(str(Path(self.folder.name)/"dragon_news_shadow.sqlite3"))
        self.requests=[]
        def respond(request):
            self.requests.append((request.method,str(request.url)))
            return httpx.Response(200,content=RSS)
        self.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))

    async def asyncTearDown(self):
        await self.client.aclose()
        self.db.close()
        self.folder.cleanup()

    async def test_collect_then_build_at_nine_without_telegram(self):
        result=await run_shadow_cycle(self.client,self.db,(SOURCE,),DAY)
        self.assertIsNotNone(result.digest)
        self.assertTrue(result.digest.created)
        self.assertEqual(result.digest.item_count,1)
        self.assertEqual(result.collection.inserted_count,1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0],0)
        self.assertEqual(self.requests,[("GET",SOURCE.url)])
        self.assertFalse(get_shadow_digest(self.db,"2026-10-15")["sent_to_telegram"])

    async def test_daily_catchup_only_before_noon(self):
        at_1159=DAY.replace(hour=11,minute=59)
        result=await run_shadow_cycle(self.client,self.db,(SOURCE,),at_1159)
        self.assertEqual(result.digest.day,"2026-10-15")
        self.assertEqual(result.digest.item_count,1)
        again=await run_shadow_cycle(self.client,self.db,(SOURCE,),at_1159)
        self.assertIsNone(again.digest)
        self.assertEqual(self.db.execute("SELECT count(*) FROM digests").fetchone()[0],1)

    async def test_no_publishing_early_or_after_noon(self):
        before=await run_shadow_cycle(self.client,self.db,(SOURCE,),DAY.replace(hour=8,minute=59))
        self.assertIsNone(before.digest)
        after=await run_shadow_cycle(self.client,self.db,(SOURCE,),DAY.replace(hour=12,minute=1))
        self.assertIsNone(after.digest)
        self.assertEqual(self.db.execute("SELECT count(*) FROM digests").fetchone()[0],0)

    async def test_partial_fetch_error_cannot_send_a_message(self):
        await self.client.aclose()
        async def err(request): return httpx.Response(503)
        self.client=httpx.AsyncClient(transport=httpx.MockTransport(err))
        result=await run_shadow_cycle(self.client,self.db,(SOURCE,),DAY)
        self.assertEqual(result.collection.failed_count,1)
        self.assertEqual(result.digest.item_count,0)
        self.assertEqual(result.digest.status,"INCOMPLETE")
        self.assertEqual(self.db.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0],0)

    async def test_utc_timestamp_after_cutoff_is_not_included(self):
        from dragon_news_v2.models import Article
        from dragon_news_v2.db import register_source,upsert_article
        from dragon_news_v2.models import Source
        register_source(self.db,Source("interfax","rss","https://interfax.ru/feed"))
        a=Article("future","interfax","https://interfax.ru/future",
                  "Госдума приняла законопроект 123456-8 о правилах в первом чтении",
                  "Подробности первого чтения и изменения правил",
                  datetime(2026,10,15,7,0,tzinfo=timezone.utc),
                  datetime(2026,10,15,5,0,tzinfo=timezone.utc),None,"future")
        upsert_article(self.db,a)
        result=await run_shadow_cycle(self.client,self.db,(),DAY)
        self.assertEqual(result.digest.item_count,0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM events").fetchone()[0],0)

if __name__=="__main__": unittest.main()
