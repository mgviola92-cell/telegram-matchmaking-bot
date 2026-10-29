"""Mocked regression checks for opt-in on-visit expiry reminders."""
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch

import handlers
import notifications
import pv_matching
import repository as db

ROOT=pathlib.Path(__file__).resolve().parents[1]

def pv(text=""):
    msg=SimpleNamespace(text=text,reply_text=AsyncMock())
    return SimpleNamespace(
        effective_chat=SimpleNamespace(type="private"),
        effective_user=SimpleNamespace(id=101),
        effective_message=msg,
    )

class NotificationContracts(unittest.TestCase):
    def test_home_keyboard_has_opt_in_menu(self):
        labels=[label for row in pv_matching.MAIN_KEYBOARD.keyboard for label in row]
        self.assertIn(notifications.MAIN_NOTIFY,labels)
        self.assertIn(notifications.ENABLE,[x for row in notifications.MENU.keyboard for x in row])
        self.assertIn(notifications.DISABLE,[x for row in notifications.MENU.keyboard for x in row])

    def test_reminders_have_no_background_poller_or_media_storage(self):
        src=(ROOT/"notifications.py").read_text(encoding="utf-8")
        schema=(ROOT/"schema.sql").read_text(encoding="utf-8")
        repo=(ROOT/"repository.py").read_text(encoding="utf-8")
        self.assertNotIn("asyncio.sleep",src)
        self.assertNotIn("send_photo",src)
        self.assertNotIn("send_video",src)
        self.assertIn("REFERENCES profiles(user_id) ON DELETE CASCADE",schema)
        self.assertIn("expiring_inbox BOOLEAN NOT NULL DEFAULT FALSE",schema)
        self.assertIn("interval '12 hours'",repo)
        self.assertIn("interval '4 hours'",repo)
        self.assertIn("status='pending'",repo)
        self.assertNotIn("public_mode",repo)


class NotificationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfirmed_user_cannot_opt_in(self):
        u=pv()
        ctx=SimpleNamespace(user_data={})
        with patch.object(db,"user_profiles",AsyncMock(return_value=[])), \
             patch.object(db,"get_notification_preference",AsyncMock()) as prefs:
            await notifications.open_menu(u,ctx)
            prefs.assert_not_awaited()
        self.assertNotIn("pv_notifications",ctx.user_data)

    async def test_private_menu_is_explicitly_opted_out_by_default(self):
        u=pv()
        ctx=SimpleNamespace(user_data={})
        with patch.object(db,"user_profiles",AsyncMock(
                        return_value=[{"adult_self_confirmed":True}])), \
             patch.object(db,"get_notification_preference",AsyncMock(
                        return_value={"expiring_inbox":False})):
            await notifications.open_menu(u,ctx)
        self.assertTrue(ctx.user_data["pv_notifications"])
        self.assertIn("ပိတ်ထားတယ်",u.effective_message.reply_text.await_args.args[0])

    async def test_enable_and_disable_only_after_menu_open(self):
        u=pv(notifications.ENABLE)
        ctx=SimpleNamespace(user_data={})
        with patch.object(db,"set_notification_preference",AsyncMock()) as write:
            self.assertFalse(await notifications.handle(u,ctx))
            write.assert_not_awaited()
        ctx.user_data["pv_notifications"]=True
        with patch.object(db,"set_notification_preference",AsyncMock(
            return_value={"user_id":101,"expiring_inbox":True})) as write:
            self.assertTrue(await notifications.handle(u,ctx))
            write.assert_awaited_once_with(101,True)
        self.assertNotIn("pv_notifications",ctx.user_data)

    async def test_digest_quiet_when_not_due(self):
        u=pv()
        ctx=SimpleNamespace()
        with patch.object(db,"claim_expiring_inbox_digest",AsyncMock(return_value=None)):
            await notifications.maybe_expiring_digest(u,ctx)
        u.effective_message.reply_text.assert_not_awaited()

    async def test_digest_emits_only_aggregate_count(self):
        u=pv()
        ctx=SimpleNamespace()
        with patch.object(db,"claim_expiring_inbox_digest",AsyncMock(return_value=2)):
            await notifications.maybe_expiring_digest(u,ctx)
        sent=u.effective_message.reply_text.await_args.args[0]
        self.assertIn("2",sent)
        self.assertNotIn("101",sent)
        self.assertNotIn("https://",sent)
        self.assertIn("၄ နာရီ",sent)

    async def test_normal_private_start_checks_digest_without_replacing_main_menu(self):
        u=pv("/start")
        ctx=SimpleNamespace(args=[],user_data={},bot=SimpleNamespace())
        with patch.object(pv_matching,"get_session",AsyncMock(return_value=None)), \
             patch.object(notifications,"maybe_expiring_digest",AsyncMock()) as check:
            await handlers.start(u,ctx)
            check.assert_awaited_once_with(u,ctx)
        self.assertIs(u.effective_message.reply_text.await_args.kwargs["reply_markup"],
                      pv_matching.MAIN_KEYBOARD)

    async def test_deep_link_not_used_for_expiring_digest(self):
        u=pv("/start")
        ctx=SimpleNamespace(args=["p_abc"],user_data={},bot=SimpleNamespace())
        with patch("growth.show_shared_profile",AsyncMock()) as shared, \
             patch.object(notifications,"maybe_expiring_digest",AsyncMock()) as check:
            await handlers.start(u,ctx)
            shared.assert_awaited_once()
            check.assert_not_awaited()

if __name__=="__main__":
    unittest.main()
