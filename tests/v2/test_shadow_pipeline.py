"""Shadow editorial integration: DB-only, no Telegram side effects."""
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dragon_news_v2.db import open_shadow_db, register_source, upsert_article
from dragon_news_v2.models import Article, Source
from dragon_news_v2.shadow_pipeline import build_shadow_digest, get_shadow_digest
from dragon_news_v2.shadow_schedule import due_shadow_cutoff

MOSCOW=ZoneInfo('Europe/Moscow')
CUTOFF=datetime(2026,10,15,9,tzinfo=MOSCOW)

def article(aid,source,title,published=None,url=None):
    return Article(aid,source,url or ('https://example.org/story/'+aid),title,
                   'Опубликованы подробности решения и конкретные условия для пользователей.',
                   published if published is not None else CUTOFF-timedelta(hours=3),
                   CUTOFF-timedelta(hours=1),None,'digest-'+aid)


class ShadowPipelineTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.db=open_shadow_db(str(Path(self.folder.name)/'dragon_news_shadow.sqlite3'))
        for s in ('tass','interfax'):
            register_source(self.db,Source(s,'rss','https://'+s+'.example.org/rss'))

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_merges_reprints_and_persists_editorial_audit(self):
        upsert_article(self.db,article('a','tass','Госдума приняла законопроект 123456-8 о новых правилах в первом чтении'))
        upsert_article(self.db,article('b','interfax','Госдума одобрила законопроект 123456-8 о новых правилах в I чтении'))
        out=build_shadow_digest(self.db,CUTOFF)
        self.assertTrue(out.created)
        self.assertEqual(out.item_count,1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM events').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM event_articles').fetchone()[0],2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM editorial_decisions').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM digest_items').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM delivery_outbox').fetchone()[0],0)
        report=get_shadow_digest(self.db,'2026-10-15')
        self.assertEqual(report['item_count'],1)
        self.assertIn('Госдума',report['rich_html'])
        self.assertIn('single_attributed',self.db.execute('SELECT status FROM events').fetchone()[0])
        self.assertFalse(report['sent_to_telegram'])

    def test_next_day_does_not_repeat_old_story_but_keeps_next_reading(self):
        one=article('a','tass','Госдума приняла законопроект 123456-8 о новых правилах в первом чтении')
        upsert_article(self.db,one)
        self.assertEqual(build_shadow_digest(self.db,CUTOFF).item_count,1)
        next_day=CUTOFF+timedelta(days=1)
        two=article('b','interfax','Госдума приняла законопроект 123456-8 о новых правилах во втором чтении',
                    published=next_day-timedelta(hours=2))
        two=Article(two.article_id,two.source_id,two.canonical_url,two.title,two.excerpt,
                    two.published_at,next_day-timedelta(hours=1),None,two.fingerprint)
        upsert_article(self.db,two)
        next_out=build_shadow_digest(self.db,next_day)
        self.assertEqual(next_out.item_count,1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM events').fetchone()[0],2)

    def test_duplicate_build_idempotent_even_if_new_articles_arrive(self):
        upsert_article(self.db,article('a','tass','Госдума приняла законопроект 123456-8 о правилах в первом чтении'))
        first=build_shadow_digest(self.db,CUTOFF)
        upsert_article(self.db,article('b','interfax','Роскомнадзор ограничил доступ к VPN-сервису Test'))
        second=build_shadow_digest(self.db,CUTOFF)
        self.assertFalse(second.created)
        self.assertEqual(first.content_hash,second.content_hash)
        self.assertEqual(self.db.execute('SELECT count(*) FROM digests').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM digest_items').fetchone()[0],first.item_count)

    def test_quality_flag_when_there_was_no_collection(self):
        result=build_shadow_digest(self.db,CUTOFF)
        self.assertEqual(result.item_count,0)
        self.assertEqual(result.status,'INCOMPLETE')
        self.assertIn('Недостаточно',get_shadow_digest(self.db,'2026-10-15')['quality_note'])

    def test_undated_and_late_fetched_excluded(self):
        missing=article('a','tass','Госдума приняла законопроект 123456-8')
        missing=Article(missing.article_id,missing.source_id,missing.canonical_url,missing.title,
                        missing.excerpt,None,missing.fetched_at,None,missing.fingerprint)
        late=article('b','interfax','РКН ограничил VPN-сервис')
        late=Article(late.article_id,late.source_id,late.canonical_url,late.title,late.excerpt,
                     late.published_at,CUTOFF+timedelta(minutes=1),None,late.fingerprint)
        upsert_article(self.db,missing)
        upsert_article(self.db,late)
        out=build_shadow_digest(self.db,CUTOFF)
        self.assertEqual(out.item_count,0)
        self.assertGreaterEqual(self.db.execute('SELECT count(*) FROM editorial_decisions').fetchone()[0],1)

    def test_rejected_decisions_logged_without_digest_padding(self):
        upsert_article(self.db,article('a','tass','YouTube Music начал внедрять ИИ-метки для музыкального контента'))
        out=build_shadow_digest(self.db,CUTOFF)
        self.assertEqual(out.item_count,0)
        self.assertEqual(self.db.execute('SELECT decision FROM editorial_decisions').fetchone()[0],'exclude')

    def test_reopen_shadow_preserves_snapshot(self):
        upsert_article(self.db,article('a','tass','Госдума приняла законопроект 123456-8 о новых правилах в первом чтении'))
        original=build_shadow_digest(self.db,CUTOFF)
        path=self.db.execute('PRAGMA database_list').fetchone()[2]
        self.db.close()
        self.db=open_shadow_db(path)
        reopened=get_shadow_digest(self.db,'2026-10-15')
        self.assertEqual(reopened['content_hash'],original.content_hash)
        self.assertFalse(build_shadow_digest(self.db,CUTOFF).created)

    def test_atomic_failure_cannot_leave_half_digest(self):
        upsert_article(self.db,article('a','tass','Госдума приняла законопроект 123456-8 о новых правилах в первом чтении',url='https://tass.ru/a'))
        # Invalid legacy-injected URL cannot be placed in any snapshot.
        self.db.execute("UPDATE articles SET canonical_url='javascript:alert(1)' WHERE article_id='a'")
        self.db.commit()
        with self.assertRaises(ValueError):
            build_shadow_digest(self.db,CUTOFF)
        self.assertEqual(self.db.execute('SELECT count(*) FROM digests').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM digest_items').fetchone()[0],0)


class ShadowScheduleTests(unittest.TestCase):
    def test_not_early_and_only_once(self):
        self.assertIsNone(due_shadow_cutoff(datetime(2026,10,15,8,59,tzinfo=MOSCOW),False))
        self.assertEqual(due_shadow_cutoff(datetime(2026,10,15,9,0,tzinfo=MOSCOW),False),CUTOFF)
        self.assertIsNone(due_shadow_cutoff(datetime(2026,10,15,9,0,tzinfo=MOSCOW),True))

    def test_catchup_until_noon_but_not_after(self):
        self.assertEqual(due_shadow_cutoff(datetime(2026,10,15,11,59,tzinfo=MOSCOW),False),CUTOFF)
        self.assertIsNone(due_shadow_cutoff(datetime(2026,10,15,12,1,tzinfo=MOSCOW),False))
        self.assertEqual(due_shadow_cutoff(datetime(2026,10,15,8,30,tzinfo=timezone.utc),False),CUTOFF)

    def test_requires_timezone(self):
        with self.assertRaises(ValueError):
            due_shadow_cutoff(datetime(2026,10,15,9,0),False)


if __name__=='__main__':
    unittest.main()
