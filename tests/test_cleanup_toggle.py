"""Expired match cards are deleted; when Telegram denies deletion only buttons are disabled."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from telegram.error import BadRequest
import handlers

class MatchExpiryCleanupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session={"message_id":17,
            "updated_at":datetime.now(timezone.utc)-timedelta(seconds=181)}

    async def test_expired_card_deleted_even_with_cleanup_setting_off(self):
        bot=SimpleNamespace(delete_message=AsyncMock(),
                            edit_message_reply_markup=AsyncMock())
        with patch.object(handlers.db,"get_browse_session",AsyncMock(return_value=self.session)):
            await handlers._expire_browse(bot,45,-100,17,0)
        bot.delete_message.assert_awaited_once_with(chat_id=-100,message_id=17)
        bot.edit_message_reply_markup.assert_not_awaited()

    async def test_deletion_failure_disables_buttons(self):
        bot=SimpleNamespace(
            delete_message=AsyncMock(side_effect=BadRequest("cannot delete")),
            edit_message_reply_markup=AsyncMock())
        with patch.object(handlers.db,"get_browse_session",AsyncMock(return_value=self.session)):
            await handlers._expire_browse(bot,45,-100,17,0)
        bot.edit_message_reply_markup.assert_awaited_once_with(
            chat_id=-100,message_id=17,reply_markup=None)

    async def test_replaced_card_is_not_deleted(self):
        bot=SimpleNamespace(delete_message=AsyncMock())
        with patch.object(handlers.db,"get_browse_session",AsyncMock(
                return_value={**self.session,"message_id":88})):
            await handlers._expire_browse(bot,45,-100,17,0)
        bot.delete_message.assert_not_awaited()

    async def test_active_card_is_not_deleted(self):
        bot=SimpleNamespace(delete_message=AsyncMock())
        fresh={"message_id":17,
               "updated_at":datetime.now(timezone.utc)-timedelta(seconds=1)}
        with patch.object(handlers.db,"get_browse_session",AsyncMock(return_value=fresh)), \
             patch.object(handlers.asyncio,"sleep",AsyncMock()):
            await handlers._expire_browse(bot,45,-100,17,0)
        bot.delete_message.assert_not_awaited()
