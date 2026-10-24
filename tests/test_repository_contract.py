"""Offline database schema contracts."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class DatabaseContractTests(unittest.TestCase):
    def test_schema(self):
        sql = (ROOT / "schema.sql").read_text(encoding="utf-8")
        for word in ("one_public_profile_per_user", "media_file_id", "browse_sessions", "group_settings", "decided_at"):
            self.assertIn(word, sql)
        self.assertNotIn("BYTEA", sql.upper())

    def test_on_demand_pool(self):
        code = (ROOT / "db.py").read_text(encoding="utf-8")
        self.assertNotIn("asyncio.sleep", code)
        self.assertIn("max_size=3", code)

    def test_cooldown(self):
        code = (ROOT / "repository.py").read_text(encoding="utf-8")
        self.assertIn("decided_at=now()", code)
        self.assertIn("interval '12 hours'", code)
        self.assertIn("interval '24 hours'", code)
