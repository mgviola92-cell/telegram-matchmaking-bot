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
