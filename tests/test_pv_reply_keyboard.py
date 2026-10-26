"""PV reply keyboard and two-sided request privacy contract."""
import pathlib
import unittest
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pv_matching
import handlers

ROOT=pathlib.Path(__file__).resolve().parents[1]

class PrivateMatchContractTests(unittest.TestCase):
    def test_keyboard_labels(self):
        rows=pv_matching.KEYBOARD.keyboard
        text=[button for row in rows for button in row]
        self.assertEqual(text,[pv_matching.SKIP,pv_matching.REQUEST,pv_matching.STOP])
        self.assertTrue(pv_matching.KEYBOARD.resize_keyboard)

    def test_source_group_only_links_sender(self):
        sender={"display_name":"မောင်မောင်"}
        recipient={"display_name":"စုစု"}
        quote=pv_matching.request_quotes(sender,recipient,7,"Club A","Club B",
            sender_id=11,recipient_id=22,sender_side=True)
        self.assertEqual(quote.count("<blockquote>"),2)
        self.assertIn('href="tg://user?id=11"',quote)
        self.assertNotIn('href="tg://user?id=22"',quote)
        self.assertIn("Group - Club A → Club B",quote)

    def test_recipient_group_only_links_recipient(self):
        quote=pv_matching.request_quotes({"display_name":"<Sender>"},
             {"display_name":"B&Me"},8,"Club A","Club B",sender_id=11,
             recipient_id=22,sender_side=False)
        self.assertEqual(quote.count("<blockquote>"),2)
        self.assertNotIn('href="tg://user?id=11"',quote)
        self.assertIn('href="tg://user?id=22"',quote)
        self.assertIn("&lt;Sender&gt;",quote)
        self.assertIn("B&amp;Me",quote)

    def test_group_match_starts_private_flow(self):
        src=(ROOT/"handlers.py").read_text(encoding="utf-8")
        self.assertIn("start=match_{gid}",src)
        self.assertIn("await pv_matching.begin(update,context,source_group)",src)
        self.assertIn("pv_matching.handle_reply",src)
        self.assertIn("pv_matching.confirm",src)

    def test_pv_session_is_stored_as_lightweight_metadata(self):
        sql=(ROOT/"schema.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS pv_match_sessions",sql)
        self.assertIn("sender_card_message_id",sql)
        self.assertNotIn("BYTEA",sql.upper())


class PvStartGuards(unittest.IsolatedAsyncioTestCase):
    async def test_reject_unverified_source_group(self):
        msg=SimpleNamespace(reply_text=AsyncMock())
        update=SimpleNamespace(effective_chat=SimpleNamespace(type="private"),
             effective_user=SimpleNamespace(id=11),effective_message=msg)
        from unittest.mock import patch
        with patch.object(handlers,"member",AsyncMock(return_value=False)):
            await pv_matching.begin(update,SimpleNamespace(bot=SimpleNamespace()),-10007)
        msg.reply_text.assert_awaited_once()
