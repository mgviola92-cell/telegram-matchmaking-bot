"""Private incoming/outgoing menus never place user-specific choices inline."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import pv_requests_menu as menu
import handlers

class ReplyRequestMenuTests(unittest.TestCase):
    def test_inbox_choices_are_reply_buttons(self):
        state={"kind":"inbox","rows":[{"id":123,"nickname":"စုစု"}]}
        keyboard=menu.options(state)
        self.assertIn("💌 #123 စုစု",state["choices"])
        self.assertEqual(state["choices"]["💌 #123 စုစု"],123)
        self.assertEqual(keyboard.keyboard[0][0].text,"💌 #123 စုစု")
        self.assertEqual(keyboard.keyboard[-1][0].text,menu.BACK)

class ReplyRequestFlows(unittest.IsolatedAsyncioTestCase):
    async def test_open_inbox_checks_current_recipient_id(self):
        msg=SimpleNamespace(reply_text=AsyncMock())
        update=SimpleNamespace(effective_chat=SimpleNamespace(type="private"),
            effective_user=SimpleNamespace(id=11),effective_message=msg)
        ctx=SimpleNamespace(user_data={})
        row={"id":17,"sender_id":22,"sender_group_id":-1007}
        with patch.object(menu.db,"incoming_requests",AsyncMock(return_value=[row])) as list_rows, \
             patch.object(menu.db,"get_profile",AsyncMock(return_value={"display_name":"မောင်မောင်"})):
            await menu.open_menu(update,ctx,"inbox")
        list_rows.assert_awaited_once_with(11)
        self.assertEqual(ctx.user_data["pv_requests"]["kind"],"inbox")
        self.assertIn("💌 #17 မောင်မောင်",ctx.user_data["pv_requests"]["choices"])

    async def test_request_resolution_revalidates_db_and_does_not_trust_keyboard_name(self):
        state={"kind":"inbox","mode":"item","request_id":17}
        context=SimpleNamespace(user_data={"pv_requests":state})
        msg=SimpleNamespace(text=menu.ACCEPT,reply_text=AsyncMock())
        update=SimpleNamespace(effective_chat=SimpleNamespace(type="private"),
            effective_user=SimpleNamespace(id=11),effective_message=msg)
        with patch.object(menu,"_answer",AsyncMock()) as answer:
            await menu.handle(update,context)
        answer.assert_awaited_once_with(update,context,17,"accepted")
        self.assertNotIn("pv_requests",context.user_data)
