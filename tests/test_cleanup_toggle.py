"""Verify group cleanup toggle without Telegram or PostgreSQL network calls."""
import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import handlers


class CleanupToggleTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_cleanup_does_not_edit_message(self):
        bot = SimpleNamespace(edit_message_reply_markup=AsyncMock())
        session = {"message_id": 17,
                   "updated_at": datetime.now(timezone.utc) - timedelta(seconds=301)}
        with patch.object(handlers.db, "get_browse_session", AsyncMock(return_value=session)), \
             patch.object(handlers.db, "group_settings", AsyncMock(return_value={"cleanup": False})):
            await handlers._expire_browse(bot, 45, -100, 17, 0)
        bot.edit_message_reply_markup.assert_not_awaited()

    async def test_enabled_cleanup_disables_old_buttons(self):
        bot = SimpleNamespace(edit_message_reply_markup=AsyncMock())
        session = {"message_id": 17,
                   "updated_at": datetime.now(timezone.utc) - timedelta(seconds=301)}
        with patch.object(handlers.db, "get_browse_session", AsyncMock(return_value=session)), \
             patch.object(handlers.db, "group_settings", AsyncMock(return_value={"cleanup": True})):
            await handlers._expire_browse(bot, 45, -100, 17, 0)
        bot.edit_message_reply_markup.assert_awaited_once_with(
            chat_id=-100, message_id=17, reply_markup=None)
