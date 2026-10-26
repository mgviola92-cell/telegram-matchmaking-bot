"""Offline checks for Telegram-native private navigation."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import handlers

class PrivateMenuTests(unittest.IsolatedAsyncioTestCase):
    def test_menu_is_telegram_inline_keyboard(self):
        keyboard = handlers.private_menu()
        names = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertTrue(any("မိတ်ဆက်ကတ်" in n for n in names))
        self.assertTrue(any("ရောက်လာတဲ့စာ" in n for n in names))
        self.assertTrue(any("ပို့ထားတဲ့စာ" in n for n in names))
        self.assertTrue(all(button.callback_data for row in keyboard.inline_keyboard for button in row))

    def test_global_profile_has_no_public_toggle(self):
        menu = handlers.profile_actions(-100123)
        callbacks = [b.callback_data for row in menu.inline_keyboard for b in row]
        self.assertIn("profile_edit:-100123:display_name",callbacks)
        self.assertIn("profile_edit:-100123:bio",callbacks)
        self.assertIn("profile_edit:-100123:media",callbacks)
        self.assertIn("profile_delete_ask:-100123",callbacks)
        self.assertIn("home:main",callbacks)
        self.assertFalse(any(c.startswith("profile_public:") for c in callbacks))

    async def test_inline_help_edits_same_message(self):
        msg = SimpleNamespace(chat=SimpleNamespace(type="private",send_message=AsyncMock()),
                              photo=[],video=None,reply_text=AsyncMock(),delete=AsyncMock())
        q = SimpleNamespace(data="home:help",message=msg,from_user=SimpleNamespace(id=17),
                            answer=AsyncMock(),edit_message_text=AsyncMock())
        await handlers.home_callback(SimpleNamespace(callback_query=q),SimpleNamespace())
        q.edit_message_text.assert_awaited_once()
        msg.reply_text.assert_not_awaited()
        msg.chat.send_message.assert_not_awaited()
        msg.delete.assert_not_awaited()

    async def test_home_from_media_removes_old_card(self):
        msg = SimpleNamespace(chat=SimpleNamespace(type="private",send_message=AsyncMock()),
                              photo=[object()],video=None,delete=AsyncMock(),reply_text=AsyncMock())
        q = SimpleNamespace(data="home:main",message=msg,from_user=SimpleNamespace(id=17),
                            answer=AsyncMock(),edit_message_text=AsyncMock())
        await handlers.home_callback(SimpleNamespace(callback_query=q),SimpleNamespace())
        msg.delete.assert_awaited_once()
        msg.chat.send_message.assert_awaited_once()
        q.edit_message_text.assert_not_awaited()

    async def test_inline_no_profiles_edits_same_message(self):
        msg = SimpleNamespace(chat=SimpleNamespace(type="private",send_message=AsyncMock()),
                              photo=[],video=None,delete=AsyncMock(),reply_text=AsyncMock())
        q = SimpleNamespace(data="home:profile",message=msg,from_user=SimpleNamespace(id=17),
                            answer=AsyncMock(),edit_message_text=AsyncMock())
        with patch.object(handlers.db,"user_profiles",AsyncMock(return_value=[])):
            await handlers.home_callback(SimpleNamespace(callback_query=q),SimpleNamespace())
        q.edit_message_text.assert_awaited_once()
        msg.reply_text.assert_not_awaited()

    async def test_withdraw_confirmation_reuses_inline_card(self):
        msg = SimpleNamespace(chat=SimpleNamespace(type="private",send_message=AsyncMock()),
                              photo=[],video=None,reply_text=AsyncMock(),delete=AsyncMock())
        q = SimpleNamespace(data="withdraw_ask:901",message=msg,
                            from_user=SimpleNamespace(id=17),answer=AsyncMock(),
                            edit_message_text=AsyncMock())
        with patch.object(handlers.db,"outgoing_requests",AsyncMock(return_value=[{"id":901}])):
            await handlers.withdraw_ask(SimpleNamespace(callback_query=q),SimpleNamespace())
        q.edit_message_text.assert_awaited_once()
        self.assertIn("withdraw_do:901",str(q.edit_message_text.await_args))
        msg.reply_text.assert_not_awaited()

    async def test_media_delete_failure_does_not_multiply_cards(self):
        from telegram.error import BadRequest
        msg = SimpleNamespace(chat=SimpleNamespace(type="private",send_message=AsyncMock()),
                              photo=[object()],video=None,
                              delete=AsyncMock(side_effect=BadRequest("message can't be deleted")),
                              reply_text=AsyncMock())
        q = SimpleNamespace(data="home:main",message=msg,
                            from_user=SimpleNamespace(id=17),answer=AsyncMock(),
                            edit_message_text=AsyncMock())
        await handlers.home_callback(SimpleNamespace(callback_query=q),SimpleNamespace())
        msg.chat.send_message.assert_not_awaited()
        msg.reply_text.assert_not_awaited()

    async def test_profile_picker_delete_failure_does_not_duplicate_media(self):
        from telegram.error import BadRequest
        msg = SimpleNamespace(chat=SimpleNamespace(type="private"),
                              delete=AsyncMock(side_effect=BadRequest("message can't be deleted")))
        q = SimpleNamespace(data="profile_view:-1007",message=msg,
                            from_user=SimpleNamespace(id=17),answer=AsyncMock())
        bot = SimpleNamespace(send_photo=AsyncMock(),send_video=AsyncMock())
        profile = {"user_id":17,"group_id":-1007,"is_public":False}
        with patch.object(handlers.db,"get_profile",AsyncMock(return_value=profile)):
            await handlers.profile_view(SimpleNamespace(callback_query=q),SimpleNamespace(bot=bot))
        bot.send_photo.assert_not_awaited()
        bot.send_video.assert_not_awaited()

    async def test_private_start_sends_menu(self):
        msg = SimpleNamespace(reply_text=AsyncMock())
        u = SimpleNamespace(effective_message=msg,
            effective_chat=SimpleNamespace(type="private"),
            effective_user=SimpleNamespace(id=4))
        ctx = SimpleNamespace(args=[])
        result = await handlers.start(u,ctx)
        self.assertEqual(result,handlers.ConversationHandler.END)
        markup = msg.reply_text.await_args.kwargs["reply_markup"]
        self.assertGreaterEqual(len(markup.inline_keyboard),3)

    async def test_private_register_shows_menu(self):
        msg = SimpleNamespace(reply_text=AsyncMock())
        u = SimpleNamespace(effective_chat=SimpleNamespace(type="private"),message=msg)
        await handlers.register(u,SimpleNamespace())
        self.assertIsNotNone(msg.reply_text.await_args.kwargs["reply_markup"])
