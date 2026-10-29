"""Owner-only QA tools must remain silent to other users and group chats."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import handlers
import owner_identity


class OwnerPanelTests(unittest.IsolatedAsyncioTestCase):
    def test_panel_is_disabled_without_owner_id(self):
        with patch.object(owner_identity,"OWNER_TELEGRAM_ID",0), patch.dict(handlers.os.environ, {"OWNER_ID":"", "TEST_GROUP_ID":"-100123"}):
            self.assertFalse(handlers.is_bot_owner(SimpleNamespace(effective_user=SimpleNamespace(id=11))))

    async def test_non_owner_gets_no_response(self):
        user = SimpleNamespace(effective_user=SimpleNamespace(id=99),
            effective_chat=SimpleNamespace(type="private"),
            effective_message=SimpleNamespace(reply_text=AsyncMock()))
        with patch.object(owner_identity,"OWNER_TELEGRAM_ID",11), patch.dict(handlers.os.environ, {"OWNER_ID":"11", "TEST_GROUP_ID":"-100123"}), \
             patch.object(handlers.db,"owner_test_request_count",AsyncMock()) as count:
            await handlers.owner_panel(user,SimpleNamespace())
        user.effective_message.reply_text.assert_not_awaited()
        count.assert_not_awaited()

    async def test_owner_panel_stays_private(self):
        user = SimpleNamespace(effective_user=SimpleNamespace(id=11),
            effective_chat=SimpleNamespace(type="supergroup"),
            effective_message=SimpleNamespace(reply_text=AsyncMock()))
        with patch.dict(handlers.os.environ, {"OWNER_ID":"11", "TEST_GROUP_ID":"-100123"}):
            await handlers.owner_panel(user,SimpleNamespace())
        user.effective_message.reply_text.assert_not_awaited()

    async def test_owner_can_open_test_panel(self):
        user = SimpleNamespace(effective_user=SimpleNamespace(id=11),
            effective_chat=SimpleNamespace(type="private"),
            effective_message=SimpleNamespace(reply_text=AsyncMock()))
        with patch.object(owner_identity,"OWNER_TELEGRAM_ID",11), patch.dict(handlers.os.environ, {"OWNER_ID":"11", "TEST_GROUP_ID":"-100123"}), \
             patch.object(handlers.db,"get_owner_qa_group",AsyncMock(return_value=-100123)), \
             patch.object(handlers.db,"owner_test_request_count",AsyncMock(return_value=3)):
            await handlers.owner_panel(user,SimpleNamespace())
        call = user.effective_message.reply_text.await_args
        self.assertIn("Owner QA Panel",str(call))
        self.assertIn("♻️ Test Request Reset",str(call))

    async def test_first_owner_visit_requests_group_once(self):
        user=SimpleNamespace(effective_user=SimpleNamespace(id=11),
            effective_chat=SimpleNamespace(type="private"),
            effective_message=SimpleNamespace(reply_text=AsyncMock()))
        with patch.object(owner_identity,"OWNER_TELEGRAM_ID",11), patch.dict(handlers.os.environ,{"OWNER_ID":"11"}), \
             patch.object(handlers.db,"get_owner_qa_group",AsyncMock(return_value=None)):
            result=await handlers.owner_panel(user,SimpleNamespace())
        self.assertEqual(result,handlers.OWNER_GROUP_INPUT)
        self.assertIn("Test Group ID",str(user.effective_message.reply_text.await_args))

    async def test_valid_owner_group_is_saved(self):
        msg=SimpleNamespace(text="-100123",reply_text=AsyncMock())
        user=SimpleNamespace(effective_user=SimpleNamespace(id=11),
            effective_chat=SimpleNamespace(type="private"),message=msg)
        bot=SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(id=55)),
            get_chat_member=AsyncMock(side_effect=[
                SimpleNamespace(status="administrator"),
                SimpleNamespace(status="member")]))
        with patch.object(owner_identity,"OWNER_TELEGRAM_ID",11), patch.dict(handlers.os.environ,{"OWNER_ID":"11"}), \
             patch.object(handlers.db,"set_owner_qa_group",AsyncMock()) as saved:
            result=await handlers.owner_group_input(user,SimpleNamespace(bot=bot))
        saved.assert_awaited_once_with(11,-100123)
        self.assertEqual(result,handlers.ConversationHandler.END)

    async def test_non_owner_cannot_save_group(self):
        msg=SimpleNamespace(text="-100123",reply_text=AsyncMock())
        user=SimpleNamespace(effective_user=SimpleNamespace(id=99),
            effective_chat=SimpleNamespace(type="private"),message=msg)
        with patch.object(owner_identity,"OWNER_TELEGRAM_ID",11), patch.dict(handlers.os.environ,{"OWNER_ID":"11"}), \
             patch.object(handlers.db,"set_owner_qa_group",AsyncMock()) as saved:
            await handlers.owner_group_input(user,SimpleNamespace())
        saved.assert_not_awaited()
        msg.reply_text.assert_not_awaited()

    async def test_other_user_cannot_reset(self):
        query = SimpleNamespace(data="owner:reset",
            message=SimpleNamespace(chat=SimpleNamespace(type="private")),
            from_user=SimpleNamespace(id=99),
            answer=AsyncMock(),edit_message_text=AsyncMock())
        update = SimpleNamespace(callback_query=query,effective_user=query.from_user)
        with patch.object(owner_identity,"OWNER_TELEGRAM_ID",11), patch.dict(handlers.os.environ, {"OWNER_ID":"11", "TEST_GROUP_ID":"-100123"}), \
             patch.object(handlers.db,"reset_owner_test_requests",AsyncMock()) as reset:
            await handlers.owner_callback(update,SimpleNamespace())
        reset.assert_not_awaited()
        query.answer.assert_not_awaited()
        query.edit_message_text.assert_not_awaited()

    def test_request_card_heading_is_concise(self):
        caption = handlers.request_card_title({"display_name":"Alice"},
            {"display_name":"Bob"},123)
        self.assertEqual(len(caption.splitlines()),3)
        self.assertIn("Alice → Bob",caption)
