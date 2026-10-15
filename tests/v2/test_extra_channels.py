"""Eight public Telegram channels: validation, filtering and editorial safety."""
import unittest
from datetime import datetime,timezone,timedelta
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from dragon_news_v2.adapters import parse_feed
from dragon_news_v2.collector import collect_once
from dragon_news_v2.db import open_shadow_db
from dragon_news_v2.editor import evaluate_event
from dragon_news_v2.evidence import assess_evidence
from dragon_news_v2.matcher import EventGroup,group_articles
from dragon_news_v2.models import Article
from dragon_news_v2.source_registry import SourceSpec,load_source_specs

NOW=datetime(2026,10,15,17,tzinfo=timezone.utc)
HANDLES=("Cbpub","cb_economics","lipetsktop1","exploitex","vgtimes","naebnet","denissexy","habr_com_news")
IDENTIFIERS=("cbpub","cb_economics","lipetsktop1","exploitex","vgtimes","naebnet","denissexy","habr_com_news")
TOPICS={
 "cbpub":"Россия — главное",
 "cb_economics":"Финансы и крипта",
 "lipetsktop1":"Липецк и Липецкая область",
 "exploitex":"Интернет и VPN",
 "vgtimes":"Игры на ПК",
 "naebnet":"Интернет и VPN",
 "denissexy":"IT, облака и AI",
 "habr_com_news":"IT, облака и AI",
}

def html_post(handle, number, body):
    return (f'<div class="tgme_widget_message" data-post="{handle}/{number}">'
            f'<div class="tgme_widget_message_text">{body}</div>'
            '<time datetime="2026-10-15T15:30:00+00:00"></time></div>')

def article(i,source,title,link=None):
    return Article(i,source,link or ('https://t.me/'+source+'/'+i),
                   title,'Подробности новости о конкретном изменении опубликованы в источнике',
                   NOW-timedelta(hours=2),NOW,None,i)


class SourceRegistryTests(unittest.TestCase):
    def test_all_eight_added_without_removing_prior_sources(self):
        registry=load_source_specs()
        ids=[s.source_id for s in registry]
        self.assertEqual(len(registry),20)
        self.assertEqual(len(ids),len(set(ids)))
        by_id={s.source_id:s for s in registry}
        for sid,handle in zip(IDENTIFIERS,HANDLES):
            self.assertIn(sid,by_id)
            self.assertEqual(by_id[sid].url,'https://t.me/s/'+handle)
            self.assertEqual(by_id[sid].kind,'public_telegram')
            self.assertIn(TOPICS[sid],by_id[sid].topics)
        for old in ('tass','interfax','rbc','habr','gorod48','kommersant'):
            self.assertIn(old,by_id)
        self.assertEqual(by_id['habr'].kind,'rss')

    def test_handles_are_source_bound_not_any_telegram_posts(self):
        spec=SourceSpec('vgtimes','https://t.me/s/vgtimes','public_telegram',('Игры на ПК',))
        payload=(html_post('vgtimes',101,'Вышел крупный патч игры с новым режимом.')
                 +html_post('exploitex',202,'Вышел другой патч игры с исправлением.')
                 +html_post('vgtimes',103,'Вышла ещё одна игра для ПК в Steam.')).encode('utf-8')
        items=parse_feed(spec,payload,NOW)
        self.assertEqual(len(items),2)
        self.assertEqual([a.canonical_url for a in items],
                         ['https://t.me/vgtimes/101','https://t.me/vgtimes/103'])

    def test_ads_memes_and_media_only_skipped_without_losing_news(self):
        spec=SourceSpec('exploitex','https://t.me/s/exploitex','public_telegram',('Интернет и VPN',))
        payload=(''.join((
          html_post('exploitex',100,'Реклама. ООО «Продавец». erid:2Vtzq48. По промокоду скидка 30%'),
          html_post('exploitex',101,'Приемлемо'),
          html_post('exploitex',102,' '),
          html_post('exploitex',103,'Вышел важный патч, закрывающий уязвимость CVE-2026-12345 в Linux.'),
          html_post('exploitex',104,'В Липецке отключили электричество в нескольких районах'),
          html_post('exploitex',105,'Сегодня Роскомнадзор сообщил о новых требованиях к VPN-сервисам в России.'),
        ))).encode('utf-8')
        urls=[a.canonical_url for a in parse_feed(spec,payload,NOW)]
        self.assertEqual(urls,['https://t.me/exploitex/103','https://t.me/exploitex/104','https://t.me/exploitex/105'])

    def test_news_about_advertising_is_not_filtered(self):
        spec=SourceSpec('cb_economics','https://t.me/s/cb_economics','public_telegram',('Финансы и крипта',))
        payload=html_post('cb_economics',77,
                          'Госдума утвердила изменения закона о рекламе банковских услуг и обязательных условиях.').encode()
        items=parse_feed(spec,payload,NOW)
        self.assertEqual(len(items),1)

    def test_no_trust_upgrade_from_regional_tg_claim(self):
        a=article('a','lipetsktop1','В Липецке отменили несколько автобусных маршрутов')
        g=EventGroup('local','',(a.article_id,),a.title,'Липецк и Липецкая область',a.published_at,a.excerpt)
        result=assess_evidence(g,{a.article_id:a},{})
        self.assertEqual(result.status,'single_attributed')
        self.assertIn('origin_unverified',result.reason_codes)

    def test_habr_rss_reprint_does_not_count_as_independent(self):
        title='В Linux исправили критическую уязвимость CVE-2026-12345'
        rss=article('rss','habr',title,'https://habr.com/ru/news/123/')
        tg=article('tg','habr_com_news',title,'https://t.me/habr_com_news/123')
        groups=group_articles([rss,tg])
        self.assertEqual(len(groups),1)
        evidence=assess_evidence(groups[0],{rss.article_id:rss,tg.article_id:tg},{})
        self.assertEqual(evidence.status,'single_attributed')
        self.assertNotEqual(evidence.status,'multi_independent')

    def test_different_habr_cve_updates_not_auto_merged(self):
        first=article('a','habr','В Linux исправили CVE-2026-12345')
        second=article('b','habr_com_news','В Windows исправили CVE-2026-12345')
        self.assertEqual(len(group_articles([first,second])),2)


class CollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_sources_idempotent_and_preserve_legacy_articles(self):
        registry=load_source_specs()
        new=[s for s in registry if s.source_id in IDENTIFIERS]
        request_count=[]
        def handler(req):
            handle=str(req.url.path).split('/')[-1]
            request_count.append(handle)
            body=html_post(handle,110,'Госдума утвердила поправки о новых требованиях к сервисам.')
            return httpx.Response(200,content=body.encode('utf-8'))
        with TemporaryDirectory() as tmp:
            db=open_shadow_db(str(Path(tmp)/'dragon_news_shadow.sqlite3'))
            try:
                db.execute("INSERT INTO sources(source_id,kind,url) VALUES (?,?,?)",
                           ('tass','rss','https://tass.ru/rss/v2.xml'))
                db.execute("""INSERT INTO articles(article_id,source_id,canonical_url,title,excerpt,raw_fingerprint,fetched_at)
                        VALUES (?,?,?,?,?,?,?)""",
                           ('old','tass','https://tass.ru/old','Оригинальная новость','','hash',NOW.isoformat()))
                db.commit()
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                    one=await collect_once(client,db,tuple(new),NOW)
                    two=await collect_once(client,db,tuple(new),NOW)
                self.assertEqual((one.ok_count,one.inserted_count),(8,8))
                self.assertEqual((two.ok_count,two.inserted_count),(8,0))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM articles").fetchone()[0],9)
                self.assertEqual(db.execute("SELECT title FROM articles WHERE article_id='old'").fetchone()[0],
                                 'Оригинальная новость')
            finally:
                db.close()


if __name__=='__main__':
    unittest.main()
