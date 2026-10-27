"""Private profile reply-keyboard contracts and isolated navigation tests."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import pv_profile,pv_matching,handlers

class ProfileReplyKeyboardTests(unittest.TestCase):
    def test_profile_actions_are_reply_keyboard_not_inline(self):
        labels=[button.text for row in pv_profile.MENU.keyboard for button in row]
        self.assertIn("✏️ နာမည်ပြင်မယ်",labels)
        self.assertIn("💬 Bio ပြင်မယ်",labels)
        self.assertIn("📸 ပုံ/Video ပြင်မယ်",labels)
        self.assertIn("🗑 Profile ဖျက်မယ်",labels)
        self.assertIn("🏠 ပင်မ Menu",labels)
        self.assertTrue(pv_profile.MENU.is_persistent)

class ProfileReplyHandlers(unittest.IsolatedAsyncioTestCase):
    async def test_open_profile_uses_reply_keyboard(self):
        msg=SimpleNamespace(reply_text=AsyncMock())
        update=SimpleNamespace(effective_chat=SimpleNamespace(type="private"),
            effective_user=SimpleNamespace(id=11),effective_message=msg)
        state={}
        ctx=SimpleNamespace(user_data=state,bot=SimpleNamespace())
        p={"group_id":-1007,"media_type":"photo","media_file_id":"test",
           "display_name":"စုစု","bio":""}
        with patch.object(pv_profile.db,"user_profiles",AsyncMock(return_value=[p])), \
             patch.object(handlers,"show_profile",AsyncMock()), \
             patch.object(handlers,"match_caption",AsyncMock(return_value="caption")):
            await pv_profile.open_profile(update,ctx)
        self.assertEqual(state["pv_profile"]["mode"],"menu")
        self.assertIs(msg.reply_text.await_args.kwargs["reply_markup"],pv_profile.MENU)

    async def test_profile_edit_uses_owner_identity_only(self):
        p={"group_id":-1007,"display_name":"စုစု"}
        state={"pv_profile":{"mode":"edit","group_id":-1007,"field":"display_name"}}
        msg=SimpleNamespace(text="နာမည်အသစ်",reply_text=AsyncMock())
        update=SimpleNamespace(effective_chat=SimpleNamespace(type="private"),
          effective_user=SimpleNamespace(id=11),effective_message=msg)
        with patch.object(pv_profile.db,"get_profile",AsyncMock(return_value=p)), \
             patch.object(pv_profile.db,"update_profile_text",
               AsyncMock(return_value=p)) as updater:
            done=await pv_profile.respond(update,SimpleNamespace(user_data=state))
        self.assertTrue(done)
        updater.assert_awaited_once_with(11,-1007,"display_name","နာမည်အသစ်")
        self.assertEqual(state["pv_profile"]["mode"],"menu")

    async def test_delete_requires_confirmation(self):
        p={"group_id":-1007}
        state={"pv_profile":{"mode":"menu","group_id":-1007}}
        msg=SimpleNamespace(text=pv_profile.DELETE,reply_text=AsyncMock())
        update=SimpleNamespace(effective_chat=SimpleNamespace(type="private"),
          effective_user=SimpleNamespace(id=11),effective_message=msg)
        with patch.object(pv_profile.db,"get_profile",AsyncMock(return_value=p)), \
             patch.object(pv_profile.db,"delete_profile",AsyncMock()) as deletion:
            await pv_profile.respond(update,SimpleNamespace(user_data=state))
        deletion.assert_not_awaited()
        self.assertEqual(state["pv_profile"]["mode"],"delete")
