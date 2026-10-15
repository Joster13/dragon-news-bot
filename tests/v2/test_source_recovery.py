"""Regression tests for repairing Kommersant, Gazeta and RBC feed health."""
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from dragon_news_v2.collector import collect_once
from dragon_news_v2.db import open_shadow_db
from dragon_news_v2.source_registry import load_source_specs, SourceSpec

NOW=datetime(2026,10,15,17,tzinfo=timezone.utc)
RSS=b'<rss><channel><item><title>New policy</title><link>https://www.kommersant.ru/doc/777</link><pubDate>Thu, 15 Oct 2026 17:00:00 +0000</pubDate></item></channel></rss>'
TELEGRAM=b'<div class="tgme_widget_message" data-post="rbc_news/555"><div class="tgme_widget_message_text">An important news update about a regulatory decision.</div><time datetime="2026-10-15T17:00:00+00:00"></time></div>'


def source(sid,url,kind='rss'):
    return SourceSpec(sid,url,kind,())


class RegistryRepairTests(unittest.TestCase):
    def test_repaired_source_registry(self):
        specs={s.source_id:s for s in load_source_specs()}
        self.assertEqual(specs['kommersant'].source_id,"kommersant")
        self.assertEqual(specs['kommersant'].url,"https://t.me/s/kommersant")
        self.assertEqual(specs['kommersant'].kind,"public_telegram")
        self.assertEqual(specs['gazeta'].url,"https://www.gazeta.ru/export/rss/first.xml")
        self.assertEqual(specs['rbc'].url,"https://t.me/s/rbc_news")
        self.assertEqual(specs['rbc'].kind,"public_telegram")
        self.assertEqual(len(specs),20)


class RetryRedirectTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self,spec,handler):
        with TemporaryDirectory() as folder:
            db=open_shadow_db(str(Path(folder)/'dragon_news_shadow.sqlite3'))
            try:
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                    report=await collect_once(client,db,(spec,),NOW)
                failures=db.execute('SELECT source_id,last_error FROM sources WHERE last_error IS NOT NULL').fetchall()
                articles=db.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
                return report,articles,failures
            finally:
                db.close()

    async def test_safe_same_host_https_redirect(self):
        seen=[]
        def handler(request):
            seen.append(str(request.url))
            if request.url.path=='/old.xml':
                return httpx.Response(301,headers={'Location':'/rss/main.xml'})
            return httpx.Response(200,content=RSS)
        report,count,fail=await self.collect(source('kommersant','https://www.kommersant.ru/old.xml'),handler)
        self.assertEqual((report.ok_count,count,fail),(1,1,[]))
        self.assertEqual(seen,['https://www.kommersant.ru/old.xml','https://www.kommersant.ru/rss/main.xml'])

    async def test_cannot_redirect_to_untrusted_external_host(self):
        seen=[]
        def handler(req):
            seen.append(str(req.url))
            return httpx.Response(301,headers={'Location':'https://evil.example/collector'})
        r,_,fail=await self.collect(source('kommersant','https://www.kommersant.ru/old.xml'),handler)
        self.assertEqual(r.failed_count,1)
        self.assertEqual(len(seen),1)
        self.assertEqual(fail[0][1],'UNSAFE_REDIRECT')

    async def test_cannot_redirect_to_localhost_or_http(self):
        for location in ('http://www.kommersant.ru/rss/main.xml','https://127.0.0.1/private','https://localhost/meta'):
            with self.subTest(location=location):
                seen=[]
                def handler(req):
                    seen.append(str(req.url))
                    return httpx.Response(302,headers={'Location':location})
                r,_,fail=await self.collect(source('kommersant','https://www.kommersant.ru/old.xml'),handler)
                self.assertEqual(r.failed_count,1)
                self.assertEqual(len(seen),1)
                self.assertEqual(fail[0][1],'UNSAFE_REDIRECT')

    async def test_redirect_loop_limited(self):
        seen=[]
        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(301,headers={'Location':'/old.xml'})
        report,_,fail=await self.collect(source('kommersant','https://www.kommersant.ru/old.xml'),handler)
        self.assertEqual(report.failed_count,1)
        self.assertLessEqual(len(seen),3)
        self.assertEqual(fail[0][1],'REDIRECT_LOOP')

    async def test_connect_timeout_retried_once(self):
        calls=[]
        def handler(req):
            calls.append(str(req.url))
            if len(calls)==1:
                raise httpx.ConnectTimeout("no response",request=req)
            return httpx.Response(200,content=RSS)
        report,count,fail=await self.collect(source('kommersant','https://www.kommersant.ru/rss/main.xml'),handler)
        self.assertEqual(report.ok_count,1)
        self.assertEqual(count,1)
        self.assertEqual(fail,[])
        self.assertEqual(len(calls),2)

    async def test_permanent_timeout_has_finite_retries(self):
        calls=[]
        def handler(req):
            calls.append(req)
            raise httpx.ConnectTimeout("no response",request=req)
        report,count,fail=await self.collect(source('kommersant','https://www.kommersant.ru/rss/main.xml'),handler)
        self.assertEqual((report.failed_count,count),(1,0))
        self.assertEqual(len(calls),2)
        self.assertEqual(fail[0][1],'ConnectTimeout')

    async def test_no_retry_http404_or_429(self):
        for status in (404,429):
            with self.subTest(status=status):
                calls=[]
                def handler(req):
                    calls.append(req)
                    return httpx.Response(status)
                report,_,fail=await self.collect(source('gazeta','https://www.gazeta.ru/export/rss/first.xml'),handler)
                self.assertEqual(report.failed_count,1)
                self.assertEqual(len(calls),1)
                self.assertEqual(fail[0][1],f'HTTP_{status}')

    async def test_rbc_public_telegram_adapter(self):
        calls=[]
        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(200,content=TELEGRAM)
        report,count,fail=await self.collect(source('rbc','https://t.me/s/rbc_news','public_telegram'),handler)
        self.assertEqual(report.ok_count,1)
        self.assertEqual(count,1)
        self.assertEqual(fail,[])
        self.assertEqual(calls,['https://t.me/s/rbc_news'])

    async def test_kommersant_public_telegram_collects_source_link(self):
        payload = ('<div class="tgme_widget_message" data-post="kommersant/82351">'
                   '<div class="tgme_widget_message_text">'
                   'Госдума приняла поправки в первом чтении. Подробности опубликованы.'
                   '</div><time datetime="2026-10-15T17:00:00+00:00"></time></div>'
                   ).encode("utf-8")
        observed=[]
        def handler(request):
            observed.append(str(request.url))
            return httpx.Response(200,content=payload)
        entry=next(s for s in load_source_specs() if s.source_id=="kommersant")
        result,count,fail=await self.collect(entry,handler)
        self.assertEqual((result.ok_count,count,fail),(1,1,[]))
        self.assertEqual(observed,["https://t.me/s/kommersant"])

    async def test_kommersant_old_rss_articles_remain_after_telegram_switch(self):
        payload = ('<div class="tgme_widget_message" data-post="kommersant/82351">'
                   '<div class="tgme_widget_message_text">Новые сведения о законопроекте.</div>'
                   '<time datetime="2026-10-15T17:00:00+00:00"></time></div>'
                   ).encode("utf-8")
        with TemporaryDirectory() as folder:
            db=open_shadow_db(str(Path(folder)/"dragon_news_shadow.sqlite3"))
            try:
                async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda req: httpx.Response(200,content=payload if req.url.host=="t.me" else RSS)
                )) as client:
                    original=source("kommersant","https://www.kommersant.ru/rss/main.xml")
                    first=await collect_once(client,db,(original,),NOW)
                    before=db.execute(
                        "SELECT article_id,canonical_url FROM articles WHERE source_id='kommersant'"
                    ).fetchall()
                    replacement=next(s for s in load_source_specs() if s.source_id=="kommersant")
                    second=await collect_once(client,db,(replacement,),NOW)
                    third=await collect_once(client,db,(replacement,),NOW)
                self.assertEqual((first.inserted_count,second.inserted_count,third.inserted_count),(1,1,0))
                self.assertEqual(
                    db.execute("SELECT article_id,canonical_url FROM articles WHERE article_id=?",
                               (before[0][0],)).fetchone(),
                    before[0]
                )
                self.assertEqual(
                    db.execute("SELECT url,kind FROM sources WHERE source_id='kommersant'").fetchone(),
                    ("https://t.me/s/kommersant","public_telegram")
                )
                self.assertEqual(
                    {row[0] for row in db.execute("SELECT canonical_url FROM articles WHERE source_id='kommersant'")},
                    {"https://www.kommersant.ru/doc/777","https://t.me/kommersant/82351"}
                )
            finally:
                db.close()

    async def test_feed_change_preserves_old_articles(self):
        with TemporaryDirectory() as folder:
            db=open_shadow_db(str(Path(folder)/'dragon_news_shadow.sqlite3'))
            calls=[]
            def handler(req):
                calls.append(str(req.url))
                return httpx.Response(200,content=TELEGRAM if req.url.host=='t.me' else RSS)
            try:
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                    before=source('rbc','https://rssexport.rbc.ru/rbcnews/news/30/full.rss')
                    await collect_once(client,db,(before,),NOW)
                    previous=db.execute('SELECT article_id,canonical_url FROM articles').fetchall()
                    after=source('rbc','https://t.me/s/rbc_news','public_telegram')
                    await collect_once(client,db,(after,),NOW)
                old=db.execute('SELECT article_id,canonical_url FROM articles WHERE article_id=?',(previous[0][0],)).fetchone()
                self.assertEqual(old,previous[0])
                self.assertEqual(db.execute('SELECT COUNT(*) FROM articles').fetchone()[0],2)
                self.assertEqual(db.execute("SELECT url,kind FROM sources WHERE source_id='rbc'").fetchone(),('https://t.me/s/rbc_news','public_telegram'))
            finally:
                db.close()


if __name__=='__main__':
    unittest.main()
