"""The exact checks exposed to the BotHost operator must pass in CI as well."""
import unittest

from selfcheck import BUILD_ID, run_selfcheck


class RunningBuildChecks(unittest.TestCase):
    def test_build_id(self):
        self.assertTrue(BUILD_ID.startswith("2026.10.15-editorial"))

    def test_editorial_regressions(self):
        report = run_selfcheck()
        self.assertIn("Редакционные проверки: 18/18", report, report)


if __name__ == "__main__":
    unittest.main()
