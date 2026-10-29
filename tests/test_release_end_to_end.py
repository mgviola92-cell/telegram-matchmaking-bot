"""Offline end-to-end flow simulations for the launch-critical Telegram paths.

All Bot API/DB calls are mocked; these are not claims of live two-user testing.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import handlers,pv_matching,pv_profile,pv_requests_menu,pv_owner
from telegram import ReplyKeyboardMarkup


class RegistrationJourney(unittest.IsolatedAsyncioTestCase):
    async def test_adult_confirmation_is_one_time_reply_keyboard(self):
        msg=SimpleNamespace(text=handlers.REG_YES,reply_text=AsyncMock())
        update=SimpleNamespace(effective_user=SimpleNamespace(id=91),message=msg)
        handlers.drafts[91]={"group_id":-10011}
        try:
            result=await handlers.confirm_age_reply(update,SimpleNamespace())
            self.assertEqual(result,handlers.NAME)
            self.assertTrue(handlers.drafts[91]["adult_confirmed"])
            self.assertIsInstance(msg.reply_text.await_args.kwargs["reply_markup"],
                                  ReplyKeyboardMarkup)
        finally:
            handlers.drafts.pop(91,None)

    async def test_declining_eligibility_never_advances_to_profile(self):
        msg=SimpleNamespace(text=handlers.REG_NO,reply_text=AsyncMock())
        update=SimpleNamespace(effective_user=SimpleNamespace(id=91),message=msg)
        handlers.drafts[91]={"group_id":-10011}
        result=await handlers.confirm_age_reply(update,SimpleNamespace())
        self.assertEqual(result,handlers.ConversationHandler.END)
        self.assertNotIn(91,handlers.drafts)


class BrowseJourney(unittest.IsolatedAsyncioTestCase):
    async def test_first_visible_card_skips_departed_group_member(self):
        uid=91
        update=SimpleNamespace(effective_chat=SimpleNamespace(type="private"),
          effective_user=SimpleNamespace(id=uid),
          effective_message=SimpleNamespace(reply_text=AsyncMock()))
        bot=SimpleNamespace(send_photo=AsyncMock(return_value=SimpleNamespace(message_id=301)))
        ctx=SimpleNamespace(bot=bot)
        candidates=[{"user_id":92,"group_id":-10021},
                    {"user_id":93,"group_id":-10031}]
        candidate={"user_id":93,"group_id":-10031,"media_type":"photo",
                   "media_file_id":"test_file","display_name":"Demo"}
        with patch.object(handlers,"member",AsyncMock(return_value=True)), \
             patch.object(pv_matching.db,"group_settings",AsyncMock(
                 return_value={"matchmaking":True,"requests":True})), \
             patch.object(pv_matching.db,"get_profile",AsyncMock(
                 return_value={"adult_self_confirmed":True})), \
             patch.object(pv_matching,"get_session",AsyncMock(return_value=None)), \
             patch.object(pv_matching.db,"browse_profiles",
                 AsyncMock(return_value=candidates)), \
             patch.object(pv_matching,"verified_target",AsyncMock(
                 side_effect=[None,candidate])), \
             patch.object(pv_matching,"finish",AsyncMock()), \
             patch.object(pv_matching,"save_session",AsyncMock()) as store, \
             patch.object(pv_matching.db,"mark_profile_viewed",AsyncMock()), \
             patch.object(handlers,"match_caption",AsyncMock(return_value="Test caption")), \
             patch.object(pv_matching,"reset_timeout"):
            await pv_matching.begin(update,ctx,-10011)
        self.assertEqual(store.await_args.kwargs["position"],1)
        self.assertEqual(bot.send_photo.await_count,1)
        self.assertEqual(bot.send_photo.await_args.args[1],"test_file")

    async def test_request_is_unchanged_by_invalid_group(self):
        q=SimpleNamespace(data="pvreq:91:-10011:92:-10021",
             from_user=SimpleNamespace(id=91),
             message=SimpleNamespace(chat=SimpleNamespace(type="private")),
             answer=AsyncMock(),edit_message_text=AsyncMock())
        update=SimpleNamespace(callback_query=q)
        session={"source_group_id":-10011,
                 "card_message_id":301,"profile_keys":[[92,-10021]],"position":0}
        with patch.object(pv_matching,"get_session",
               AsyncMock(return_value=session)), \
             patch.object(pv_matching.db,"group_settings",AsyncMock(
               side_effect=[{"requests":True,"matchmaking":True},
                            {"requests":False,"matchmaking":True}])), \
             patch.object(pv_matching.db,"send_request",AsyncMock()) as send:
            await pv_matching.confirm(update,SimpleNamespace(bot=SimpleNamespace()))
        send.assert_not_awaited()
        q.answer.assert_awaited_once()

class RestartRecoveryJourney(unittest.IsolatedAsyncioTestCase):
    async def test_orphan_keyboard_returns_home_instead_of_hanging(self):
        msg=SimpleNamespace(text="⬅️ နောက်ပြန်",reply_text=AsyncMock())
        update=SimpleNamespace(effective_chat=SimpleNamespace(type="private"),
            effective_message=msg,effective_user=SimpleNamespace(id=91))
        ctx=SimpleNamespace(user_data={})
        await handlers.pv_profile_text_command(update,ctx)
        self.assertIs(msg.reply_text.await_args.kwargs["reply_markup"],
                      pv_matching.MAIN_KEYBOARD)

class PrivateResponseJourney(unittest.IsolatedAsyncioTestCase):
    async def test_private_request_entry_uses_reply_keyboard(self):
        msg=SimpleNamespace(reply_text=AsyncMock())
        update=SimpleNamespace(effective_chat=SimpleNamespace(type="private"),
            effective_message=msg,effective_user=SimpleNamespace(id=92))
        ctx=SimpleNamespace(user_data={})
        with patch.object(pv_requests_menu.db,"pending_request_for_recipient",
                AsyncMock(return_value={"id":7})), \
             patch.object(pv_requests_menu,"show_item",AsyncMock(return_value=True)) as show:
            ok=await pv_requests_menu.open_incoming_direct(update,ctx,7)
        self.assertTrue(ok)
        self.assertEqual(ctx.user_data["pv_requests"]["kind"],"inbox")
        show.assert_awaited_once()
