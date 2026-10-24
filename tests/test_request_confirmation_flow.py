"""Isolated handler tests: no live Telegram token or database required."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import handlers


def fake_update(callback_data, user_id=11, message_id=50):
    msg = SimpleNamespace(
        chat=SimpleNamespace(id=-1007, type="supergroup"),
        message_id=message_id,
        reply_text=AsyncMock(),
    )
    q = SimpleNamespace(
        data=callback_data,
        from_user=SimpleNamespace(id=user_id),
        message=msg,
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    return SimpleNamespace(callback_query=q)


class RequestConfirmationTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_tap_does_not_send_request(self):
        update = fake_update("ask:11:-1007:22:-1007")
        ctx = SimpleNamespace(bot=MagicMock())
        ctx.bot.get_me = AsyncMock()
        session = {"message_id":50, "profile_keys":[[22,-1007]],"position":0}
        with patch.object(handlers.db,"active_browse_session",AsyncMock(return_value=session)), \
             patch.object(handlers.db,"get_profile",AsyncMock(return_value={"display_name":"Tester"})), \
             patch.object(handlers.db,"group_settings",AsyncMock(return_value={"requests":True})), \
             patch.object(handlers.db,"send_request",AsyncMock()) as send, \
             patch.object(handlers,"member",AsyncMock(return_value=True)):
            await handlers.ask_callback(update,ctx)
        send.assert_not_awaited()
        update.callback_query.message.reply_text.assert_awaited_once()
        self.assertIn("ask_confirm:",str(update.callback_query.message.reply_text.await_args))

    async def test_other_user_cannot_cancel(self):
        update = fake_update("ask_cancel:11:-1007:22:-1007",user_id=99)
        update.callback_query.edit_message_text=AsyncMock()
        ctx = SimpleNamespace(bot=MagicMock())
        await handlers.ask_confirm_callback(update,ctx)
        update.callback_query.edit_message_text.assert_not_awaited()
        update.callback_query.answer.assert_awaited_once()

    async def test_owner_can_cancel(self):
        update = fake_update("ask_cancel:11:-1007:22:-1007",user_id=11)
        update.callback_query.edit_message_text=AsyncMock()
        await handlers.ask_confirm_callback(update,SimpleNamespace(bot=MagicMock()))
        update.callback_query.edit_message_text.assert_awaited_once()

    async def test_intro_request_first_tap_asks_for_confirmation(self):
        update = fake_update("intro_view:22:-1007",user_id=11)
        ctx = SimpleNamespace(bot=MagicMock())
        with patch.object(handlers.db,"group_settings",AsyncMock(return_value={"requests":True,"intros":True})), \
             patch.object(handlers,"member",AsyncMock(return_value=True)), \
             patch.object(handlers.db,"get_profile",AsyncMock(return_value={"display_name":"Tester"})), \
             patch.object(handlers.db,"send_request",AsyncMock()) as send:
            await handlers.intro_view(update,ctx)
        send.assert_not_awaited()
        self.assertIn("intro_confirm:",str(update.callback_query.message.reply_text.await_args))

    async def test_other_user_cannot_approve_intro_request(self):
        update = fake_update("intro_confirm:11:-1007:22",user_id=99)
        ctx = SimpleNamespace(bot=MagicMock())
        with patch.object(handlers.db,"send_request",AsyncMock()) as send:
            await handlers.intro_confirm_callback(update,ctx)
        send.assert_not_awaited()

    async def test_other_user_cannot_confirm(self):
        update = fake_update("ask_confirm:11:-1007:22:-1007",user_id=99)
        ctx = SimpleNamespace(bot=MagicMock())
        with patch.object(handlers.db,"send_request",AsyncMock()) as send:
            await handlers.ask_confirm_callback(update,ctx)
        send.assert_not_awaited()
        update.callback_query.answer.assert_awaited_once()

    async def test_confirmation_rechecks_profile_state(self):
        update = fake_update("ask_confirm:11:-1007:22:-1007")
        ctx = SimpleNamespace(bot=MagicMock())
        session={"message_id":50,"profile_keys":[[22,-1007]],"position":0}
        with patch.object(handlers.db,"active_browse_session",AsyncMock(return_value=session)), \
             patch.object(handlers.db,"group_settings",AsyncMock(return_value={"requests":True})), \
             patch.object(handlers,"member",AsyncMock(return_value=True)), \
             patch.object(handlers.db,"get_profile",AsyncMock(return_value=None)), \
             patch.object(handlers.db,"send_request",AsyncMock()) as send:
            await handlers.ask_confirm_callback(update,ctx)
        send.assert_not_awaited()
