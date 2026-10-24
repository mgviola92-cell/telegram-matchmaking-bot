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

    def test_profile_toggle_preserves_management_buttons(self):
        for is_public in (False, True):
            menu = handlers.profile_actions(-100123,is_public)
            callbacks = [b.callback_data for row in menu.inline_keyboard for b in row]
            self.assertIn("profile_edit:-100123:display_name",callbacks)
            self.assertIn("profile_edit:-100123:bio",callbacks)
            self.assertIn("profile_edit:-100123:media",callbacks)
            self.assertIn("profile_delete_ask:-100123",callbacks)
            self.assertIn("home:main",callbacks)
            self.assertIn("profile_public:-100123:"+("0" if is_public else "1"),callbacks)

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
