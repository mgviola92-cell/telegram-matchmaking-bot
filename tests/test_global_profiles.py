"""One user has one global profile; group controls affect requests, not visibility."""
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import handlers

ROOT = pathlib.Path(__file__).resolve().parents[1]

class GlobalProfileContract(unittest.TestCase):
    def test_no_group_only_public_switch(self):
        keyboard=handlers.match_buttons(11,-1007,{"user_id":22,"group_id":-1008},0,2)
        callbacks=[b.callback_data for row in keyboard.inline_keyboard for b in row]
        self.assertFalse(any(c.startswith("browse_mode:") for c in callbacks))
        self.assertEqual(len(callbacks),3)

    def test_profile_controls_are_global(self):
        handlers_source=(ROOT/"handlers.py").read_text(encoding="utf-8")
        self.assertNotIn("profile_public:",handlers_source)
        self.assertNotIn('["is_public"]',handlers_source)
        self.assertNotIn('["public_mode"]',handlers_source)
        self.assertNotIn('"public_browse":',handlers_source)

    def test_database_filters_no_group_only(self):
        repo=(ROOT/"repository.py").read_text(encoding="utf-8")
        self.assertIn("CREATE UNIQUE INDEX", (ROOT/"schema.sql").read_text(encoding="utf-8"))
        self.assertIn("ON CONFLICT(user_id)",repo)
        self.assertNotIn("p.group_id=$2 OR",repo)
        self.assertNotIn("public_mode",repo)
        self.assertNotIn("public_browse",repo)
        self.assertNotIn("is_public",repo)
        self.assertIn("WHERE user_id=$1 AND NOT archived",repo)


    def test_routing_group_is_separate_from_profile_identity(self):
        repo=(ROOT/"repository.py").read_text(encoding="utf-8")
        self.assertIn("LEFT JOIN LATERAL",repo)
        self.assertIn("profile_presence",repo)
        self.assertIn("COALESCE(venue.group_id,p.group_id)",repo)
        schema=(ROOT/"schema.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS profile_presence",schema)

    def test_pre_migration_profile_metadata_is_preserved(self):
        schema=(ROOT/"schema.sql").read_text(encoding="utf-8")
        self.assertIn("profiles_legacy_backup",schema)
        self.assertIn("one_global_profile_per_user",schema)
        self.assertIn("ROW_NUMBER() OVER (PARTITION BY user_id",schema)
        self.assertIn("DROP COLUMN IF EXISTS is_public",schema)
        self.assertIn("DROP COLUMN IF EXISTS public_mode",schema)
        self.assertIn("DROP COLUMN IF EXISTS public_browse",schema)

class GlobalProfileRegistrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_second_group_does_not_request_registration(self):
        msg=SimpleNamespace(reply_text=AsyncMock())
        user=SimpleNamespace(id=11)
        update=SimpleNamespace(effective_chat=SimpleNamespace(id=-1008,type="supergroup"),
            effective_user=user,message=msg)
        with patch.object(handlers.db,"group_settings",AsyncMock(return_value={"registration":True})), \
             patch.object(handlers.db,"get_profile",AsyncMock(return_value={"user_id":11,"group_id":-1007})), \
             patch.object(handlers.db,"record_profile_presence",AsyncMock()) as marker:
            await handlers.register(update,SimpleNamespace())
        marker.assert_awaited_once_with(11,-1008)
        self.assertIn("/match",str(msg.reply_text.await_args))
        self.assertNotIn("join_",str(msg.reply_text.await_args))
