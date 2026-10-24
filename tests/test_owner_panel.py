"""Owner-only QA tools must remain silent to other users and group chats."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import handlers


class OwnerPanelTests(unittest.IsolatedAsyncioTestCase):
    def test_panel_is_disabled_without_owner_id(self):
        with patch.dict(handlers.os.environ, {"OWNER_ID":"", "TEST_GROUP_ID":"-100123"}):
            self.assertFalse(handlers.is_bot_owner(SimpleNamespace(effective_user=SimpleNamespace(id=11))))

    async def test_non_owner_gets_no_response(self):
        user = SimpleNamespace(effective_user=SimpleNamespace(id=99),
            effective_chat=SimpleNamespace(type="private"),
            effective_message=SimpleNamespace(reply_text=AsyncMock()))
        with patch.dict(handlers.os.environ, {"OWNER_ID":"11", "TEST_GROUP_ID":"-100123"}), \
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
        with patch.dict(handlers.os.environ, {"OWNER_ID":"11", "TEST_GROUP_ID":"-100123"}), \
             patch.object(handlers.db,"owner_test_request_count",AsyncMock(return_value=3)):
            await handlers.owner_panel(user,SimpleNamespace())
        call = user.effective_message.reply_text.await_args
        self.assertIn("Owner QA Panel",str(call))
        self.assertIn("owner:ask_reset",str(call))

    async def test_other_user_cannot_reset(self):
        query = SimpleNamespace(data="owner:reset",
            message=SimpleNamespace(chat=SimpleNamespace(type="private")),
            from_user=SimpleNamespace(id=99),
            answer=AsyncMock(),edit_message_text=AsyncMock())
        update = SimpleNamespace(callback_query=query,effective_user=query.from_user)
        with patch.dict(handlers.os.environ, {"OWNER_ID":"11", "TEST_GROUP_ID":"-100123"}), \
             patch.object(handlers.db,"reset_owner_test_requests",AsyncMock()) as reset:
            await handlers.owner_callback(update,SimpleNamespace())
        reset.assert_not_awaited()
        query.answer.assert_not_awaited()
        query.edit_message_text.assert_not_awaited()

    def test_request_card_heading_is_concise(self):
        caption = handlers.request_card_title({"display_name":"Alice"},
            {"display_name":"Bob"},123)
        self.assertEqual(caption.count("\\n"),1)
        self.assertIn("Alice → Bob",caption)
