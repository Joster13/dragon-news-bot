"""Shadow mode must be fully opt-in and must not create another bot poller."""
import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from dragon_news_v2.integration import shadow_enabled, shadow_db_path, start_shadow_collector

class ShadowWiringTests(unittest.IsolatedAsyncioTestCase):
    def test_default_no_shadow_side_effects(self):
        with patch.dict(os.environ, {'V2_SHADOW_ENABLED':'false'}):
            self.assertFalse(shadow_enabled())

    def test_shadow_enable_uses_distinct_db(self):
        with TemporaryDirectory() as folder:
            legacy=str(Path(folder)/'dragon_news.sqlite3')
            shadow=str(Path(folder)/'dragon_news_shadow.sqlite3')
            with patch.dict(os.environ,{'DB_PATH':legacy,'V2_DB_PATH':legacy,'V2_SHADOW_ENABLED':'true'}):
                with self.assertRaises(ValueError):
                    shadow_db_path()
            with patch.dict(os.environ,{'DB_PATH':legacy,'V2_DB_PATH':shadow,'V2_SHADOW_ENABLED':'true'}):
                self.assertEqual(shadow_db_path(),shadow)
                self.assertFalse(Path(shadow).exists())

    async def test_task_closes_shadow_db_on_shutdown(self):
        with TemporaryDirectory() as folder:
            shadow=str(Path(folder)/'dragon_news_shadow.sqlite3')
            with patch.dict(os.environ,{'DB_PATH':str(Path(folder)/'dragon_news.sqlite3'), 'V2_DB_PATH':shadow}):
                stop=asyncio.Event()
                with patch('dragon_news_v2.integration.run_shadow_workflow',side_effect=self._exit_immediately):
                    task=start_shadow_collector(object(),stop)
                    await asyncio.wait_for(task,timeout=2)
                self.assertTrue(Path(shadow).exists())
                from dragon_news_v2.db import open_shadow_db
                db=open_shadow_db(shadow)
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                db.close()

    async def _exit_immediately(self,client,db,stop):
        stop.set()

    def test_integrates_daily_snapshot_runner_not_only_collector(self):
        import inspect
        import dragon_news_v2.integration as module
        code=inspect.getsource(module.start_shadow_collector)
        self.assertIn('run_shadow_workflow',code)
        self.assertNotIn('run_collector_loop',code)

    def test_main_integration_only_by_flag(self):
        import inspect
        import main
        run = inspect.getsource(main.NewsBot.run)
        self.assertIn('if shadow_enabled():', run)
        self.assertEqual(inspect.getsource(main.NewsBot.listen).count('getUpdates'), 1)
        self.assertIn('self.listen(), self.scheduler()', run)
        for old in ('"start"', '"today"', '"status"', '"export"'):
            self.assertIn(old, run)

    def test_single_polling_consumer(self):
        import inspect
        import dragon_news_v2.integration as module
        self.assertNotIn('getUpdates',inspect.getsource(module))
        self.assertNotIn('deleteWebhook',inspect.getsource(module))

if __name__=='__main__': unittest.main()
