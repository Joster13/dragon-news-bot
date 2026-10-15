"""Seven-day shadow trial harness: no Telegram token, no production database."""
import asyncio
import inspect
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from dragon_news_v2.db import open_shadow_db
from dragon_news_v2.trial import trial_status, require_shadow_only_path
from shadow_runner import main as runner_main

TZ=ZoneInfo("Europe/Moscow")
START=datetime(2026,10,15,18,30,tzinfo=TZ)


class TrialStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db_path=Path(self.tmp.name)/"dragon_news_shadow.sqlite3"
        self.db=open_shadow_db(str(self.db_path))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_seven_distinct_daily_digests_are_required(self):
        for i in range(7):
            stamp=START+timedelta(days=i)
            with self.db:
                self.db.execute(
                    "INSERT INTO collector_runs(run_id,started_at,status,sources_ok) "
                    "VALUES(?,?,?,?)",(f"run-{i}",stamp.isoformat(),"OK",12))
                self.db.execute(
                    "INSERT INTO digests(digest_id,day,cutoff_at,built_at,build_version,status,quality_note) "
                    "VALUES (?,?,?,?,?,?,?)",(f"digest-{i}",stamp.date().isoformat(),
                         stamp.isoformat(),stamp.isoformat(),"v2","READY",""))
        result=trial_status(self.db,START+timedelta(days=7))
        self.assertEqual(result["completed_days"],7)
        self.assertEqual(result["days_seen"],7)
        self.assertTrue(result["seven_day_window_elapsed"])
        self.assertEqual(result["collector_runs"],7)
        self.assertEqual(result["incomplete_days"],[])
        self.assertFalse(result["quality_review_complete"])

    def test_missing_or_incomplete_digests_fail_readiness(self):
        for i,status in ((0,"READY"),(1,"INCOMPLETE"),(3,"READY")):
            stamp=START+timedelta(days=i)
            with self.db:
                self.db.execute("INSERT INTO digests(digest_id,day,cutoff_at,built_at,build_version,status,quality_note) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (f"d-{i}",stamp.date().isoformat(),stamp.isoformat(),
                     stamp.isoformat(),"v2",status,""))
        with self.db:
            self.db.execute("INSERT INTO collector_runs(run_id,started_at,status) VALUES(?,?,?)",
                            ("run-0",START.isoformat(),"OK"))
        report=trial_status(self.db,START+timedelta(days=7))
        self.assertEqual(report["completed_days"],2)
        self.assertIn((START+timedelta(days=1)).date().isoformat(),report["incomplete_days"])
        self.assertFalse(report["ready_for_review"])

    def test_no_runs_is_not_started(self):
        status=trial_status(self.db,START)
        self.assertEqual(status["status"],"not_started")
        self.assertFalse(status["ready_for_review"])

    def test_status_does_not_change_database(self):
        before=self.db.execute("SELECT count(*) FROM collector_runs").fetchone()[0]
        trial_status(self.db,START)
        after=self.db.execute("SELECT count(*) FROM collector_runs").fetchone()[0]
        self.assertEqual(before,after)

    def test_only_named_shadow_database_accepted(self):
        require_shadow_only_path(str(self.db_path))
        with self.assertRaises(ValueError):
            require_shadow_only_path(str(self.db_path.parent/"dragon_news.sqlite3"))
        with self.assertRaises(ValueError):
            require_shadow_only_path(str(self.db_path.parent/"my_news.sqlite3"))


class StandaloneRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_runner_never_imports_telegram_or_existing_bot(self):
        import shadow_runner
        source=inspect.getsource(shadow_runner)
        self.assertNotIn("from main import",source)
        self.assertNotIn("getUpdates",source)
        self.assertNotIn("sendMessage",source)
        self.assertNotIn("BOT_TOKEN",source)

    async def test_status_requires_existing_shadow_file(self):
        with tempfile.TemporaryDirectory() as directory:
            missing=str(Path(directory)/"dragon_news_shadow.sqlite3")
            with patch("sys.argv",["shadow_runner.py","--status","--db",missing]):
                with self.assertRaises(FileNotFoundError):
                    await runner_main()
            self.assertFalse(Path(missing).exists())

    async def test_status_prints_only_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/"dragon_news_shadow.sqlite3")
            db=open_shadow_db(path); db.close()
            from io import StringIO
            stream=StringIO()
            with patch("sys.argv",["shadow_runner.py","--status","--db",path]):
                with patch("sys.stdout",stream):
                    await runner_main()
            report=json.loads(stream.getvalue())
            self.assertEqual(report["status"],"not_started")
            self.assertFalse(report["ready_for_review"])

    async def test_sources_report_lists_health_without_sql_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/"dragon_news_shadow.sqlite3")
            db=open_shadow_db(path)
            with db:
                db.execute("INSERT INTO sources(source_id,kind,url,last_error,last_success_at) VALUES(?,?,?,?,?)",
                           ("rbc","public_telegram","https://t.me/s/rbc_news",None,START.isoformat()))
                db.execute("INSERT INTO sources(source_id,kind,url,last_error,last_success_at) VALUES(?,?,?,?,?)",
                           ("gazeta","rss","https://www.gazeta.ru/export/rss/first.xml","HTTP_404",None))
            db.close()
            from io import StringIO
            stream=StringIO()
            with patch("sys.argv",["shadow_runner.py","--sources","--db",path]):
                with patch("sys.stdout",stream):
                    await runner_main()
            report=json.loads(stream.getvalue())
            self.assertEqual(len(report["sources"]),2)
            rbc=next(x for x in report["sources"] if x["source_id"]=="rbc")
            self.assertEqual(rbc["state"],"ok")
            gazeta=next(x for x in report["sources"] if x["source_id"]=="gazeta")
            self.assertEqual(gazeta["state"],"error")
            self.assertEqual(gazeta["last_error"],"HTTP_404")

    async def test_preview_date_reads_saved_items_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/"dragon_news_shadow.sqlite3")
            db=open_shadow_db(path)
            with db:
                db.execute("INSERT INTO digests(digest_id,day,cutoff_at,built_at,build_version,status,quality_note) VALUES(?,?,?,?,?,?,?)",
                    ("shadow:2026-10-15","2026-10-15",START.isoformat(),START.isoformat(),"v2","READY",""))
                db.execute("INSERT INTO events(event_id,event_key,headline,first_seen_at,last_seen_at,status) VALUES(?,?,?,?,?,?)",
                    ("ev01","event:01","В Липецке изменили расписание транспорта",START.isoformat(),START.isoformat(),"single_attributed"))
                db.execute("INSERT INTO digest_items(digest_id,event_id,position,rendered_text) VALUES(?,?,?,?)",
                    ("shadow:2026-10-15","ev01",1,json.dumps({"headline":"В Липецке изменили расписание транспорта",
                          "category":"Липецк и Липецкая область","source_urls":["https://tass.ru/123"],
                          "facts":"Опубликовано новое расписание","evidence_status":"single_attributed"},ensure_ascii=False)))
            db.close()
            from io import StringIO
            stream=StringIO()
            with patch("sys.argv",["shadow_runner.py","--preview-date","2026-10-15","--db",path]):
                with patch("sys.stdout",stream):
                    await runner_main()
            report=json.loads(stream.getvalue())
            self.assertEqual(len(report["items"]),1)
            self.assertEqual(report["items"][0]["source_urls"],["https://tass.ru/123"])
            self.assertEqual(report["day"],"2026-10-15")

    async def test_run_mode_uses_no_telegram_token_and_single_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/"dragon_news_shadow.sqlite3")
            observed=[]
            async def fake_run(client,db,stop):
                observed.append(db.execute("PRAGMA database_list").fetchone()[2])
                stop.set()
            with patch("sys.argv",["shadow_runner.py","--db",path]):
                with patch("shadow_runner.run_shadow_workflow",side_effect=fake_run):
                    await runner_main()
            self.assertEqual(observed,[str(Path(path).resolve())])


if __name__=="__main__":
    unittest.main()
