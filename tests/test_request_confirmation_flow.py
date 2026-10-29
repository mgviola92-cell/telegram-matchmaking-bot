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

    def test_request_caption_names_both_participants(self):
        text = handlers.request_card_title(
            {"display_name":"ပို့သူ <one>"},
            {"display_name":"လက်ခံသူ & two"}, 123)
        self.assertIn("ပို့သူ &lt;one&gt;",text)
        self.assertIn("လက်ခံသူ &amp; two",text)
        self.assertIn("#123",text)
        self.assertIn("→",text)

    async def test_request_media_has_context_and_reply_link(self):
        bot = SimpleNamespace(send_photo=AsyncMock())
        p = {"display_name":"Sender","bio":"","media_type":"photo","media_file_id":"file-1"}
        await handlers.show_profile(bot,-1007,p,None,
            header=handlers.request_card_title(p,{"display_name":"Target"},77),
            reply_to_message_id=50)
        args=bot.send_photo.await_args
        self.assertEqual(args.kwargs["reply_to_message_id"],50)
        self.assertIn("Sender",args.kwargs["caption"])
        self.assertIn("Target",args.kwargs["caption"])
        self.assertEqual(args.kwargs["parse_mode"],"HTML")

    async def test_reply_button_prompt_references_request_card(self):
        update = fake_update("reply:123:11",user_id=11,message_id=55)
        bot=SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="example_bot")))
        prompt = SimpleNamespace(message_id=88)
        update.callback_query.message.reply_text.return_value=prompt
        with patch.object(handlers.db,"remember_request_group_message",AsyncMock()) as saved, \
             patch.object(handlers.db,"pending_request_for_recipient",AsyncMock(return_value={"id":123})), \
             patch.object(handlers.db,"get_request_group_messages",AsyncMock(return_value=None)):
            await handlers.reply_callback(update,SimpleNamespace(bot=bot))
        saved.assert_awaited_once_with(123,11,"prompt",88)
        msg=update.callback_query.message
        self.assertEqual(msg.reply_text.await_args.kwargs["reply_to_message_id"],55)
        self.assertIn("reply_123",str(msg.reply_text.await_args))

    async def test_duplicate_group_reply_does_not_create_another_prompt(self):
        update=fake_update("reply:123:11",user_id=11,message_id=55)
        bot=SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="sample_bot")))
        refs={"group_prompt_message_id":56}
        with patch.object(handlers.db,"pending_request_for_recipient",AsyncMock(return_value={"id":123})), \
             patch.object(handlers.db,"get_request_group_messages",AsyncMock(return_value=refs)):
            await handlers.reply_callback(update,SimpleNamespace(bot=bot))
        update.callback_query.message.reply_text.assert_not_awaited()

    async def test_group_handoff_disables_card_and_deletes_prompt(self):
        refs={"recipient_group_id":-1007,"group_card_message_id":55,
              "group_prompt_message_id":56}
        bot=SimpleNamespace(edit_message_reply_markup=AsyncMock(),
                            delete_message=AsyncMock())
        with patch.object(handlers.db,"get_request_group_messages",AsyncMock(return_value=refs)):
            await handlers.cleanup_request_group_messages(bot,9,11)
        bot.delete_message.assert_any_await(chat_id=-1007,message_id=55)
        bot.delete_message.assert_any_await(chat_id=-1007,message_id=56)
        bot.edit_message_reply_markup.assert_not_awaited()

    async def test_handoff_fallback_disables_prompt_button(self):
        from telegram.error import BadRequest
        refs={"recipient_group_id":-1007,"group_card_message_id":55,
              "group_prompt_message_id":56}
        bot=SimpleNamespace(edit_message_reply_markup=AsyncMock(),
                            delete_message=AsyncMock(side_effect=BadRequest("not deletable")))
        with patch.object(handlers.db,"get_request_group_messages",AsyncMock(return_value=refs)):
            await handlers.cleanup_request_group_messages(bot,9,11)
        self.assertEqual(bot.edit_message_reply_markup.await_count,2)

    async def test_open_private_reply_cleans_group_messages(self):
        msg=SimpleNamespace(reply_text=AsyncMock())
        update=SimpleNamespace(effective_message=msg,
            effective_chat=SimpleNamespace(id=11,type="private"),
            effective_user=SimpleNamespace(id=11))
        bot=SimpleNamespace()
        with patch.object(handlers.pv_requests_menu,"open_incoming_direct",
                AsyncMock(return_value=True)) as open_private, \
             patch.object(handlers,"cleanup_request_group_messages",
                AsyncMock()) as cleanup:
            await handlers.start(update,SimpleNamespace(
                args=["reply_9"],bot=bot,user_data={}))
        open_private.assert_awaited_once()
        cleanup.assert_awaited_once_with(bot,9,11)

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
