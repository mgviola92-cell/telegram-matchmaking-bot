"""PV reply keyboard and two-sided request privacy contract."""
import pathlib
import unittest
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pv_matching
import handlers

ROOT=pathlib.Path(__file__).resolve().parents[1]

class PrivateMatchContractTests(unittest.TestCase):
    def test_keyboard_labels(self):
        rows=pv_matching.KEYBOARD.keyboard
        text=[button.text for row in rows for button in row]
        self.assertEqual(text,[pv_matching.SKIP,pv_matching.REQUEST,pv_matching.STOP])
        self.assertTrue(pv_matching.KEYBOARD.resize_keyboard)

    def test_source_group_only_links_sender(self):
        sender={"display_name":"မောင်မောင်"}
        recipient={"display_name":"စုစု"}
        quote=pv_matching.request_quotes(sender,recipient,7,"Club A","Club B",
            sender_id=11,recipient_id=22,sender_side=True)
        self.assertEqual(quote.count("<blockquote>"),2)
        self.assertIn('href="tg://user?id=11"',quote)
        self.assertNotIn('href="tg://user?id=22"',quote)
        self.assertIn("Group - Club A → Club B",quote)

    def test_recipient_group_only_links_recipient(self):
        quote=pv_matching.request_quotes({"display_name":"<Sender>"},
             {"display_name":"B&Me"},8,"Club A","Club B",sender_id=11,
             recipient_id=22,sender_side=False)
        self.assertEqual(quote.count("<blockquote>"),2)
        self.assertNotIn('href="tg://user?id=11"',quote)
        self.assertIn('href="tg://user?id=22"',quote)
        self.assertIn("&lt;Sender&gt;",quote)
        self.assertIn("B&amp;Me",quote)

    def test_group_match_starts_private_flow(self):
        src=(ROOT/"handlers.py").read_text(encoding="utf-8")
        self.assertIn("start=match_{gid}",src)
        self.assertIn("await pv_matching.begin(update,context,source_group)",src)
        self.assertIn("pv_matching.handle_reply",src)
        self.assertIn("pv_matching.confirm",src)

    def test_pv_session_is_stored_as_lightweight_metadata(self):
        sql=(ROOT/"schema.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS pv_match_sessions",sql)
        self.assertIn("sender_card_message_id",sql)
        self.assertNotIn("BYTEA",sql.upper())


class PvStartGuards(unittest.IsolatedAsyncioTestCase):
    async def test_reject_unverified_source_group(self):
        msg=SimpleNamespace(reply_text=AsyncMock())
        update=SimpleNamespace(effective_chat=SimpleNamespace(type="private"),
             effective_user=SimpleNamespace(id=11),effective_message=msg)
        from unittest.mock import patch
        with patch.object(handlers,"member",AsyncMock(return_value=False)):
            await pv_matching.begin(update,SimpleNamespace(bot=SimpleNamespace()),-10007)
        msg.reply_text.assert_awaited_once()

class DualGroupDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirm_posts_recipient_photo_to_sender_group_and_sender_photo_to_recipient_group(self):
        from unittest.mock import patch,MagicMock
        sender={"display_name":"မောင်မောင်","bio":"", "adult_self_confirmed":True,
                "media_type":"photo","media_file_id":"sender_photo"}
        recipient={"display_name":"စုစု","bio":"", "adult_self_confirmed":True,
                   "media_type":"photo","media_file_id":"recipient_photo"}
        q=SimpleNamespace(data="pvreq:11:-1007:22:-1009",
              from_user=SimpleNamespace(id=11),
              message=SimpleNamespace(chat=SimpleNamespace(type="private")),
              answer=AsyncMock(),edit_message_text=AsyncMock())
        update=SimpleNamespace(callback_query=q)
        session={"source_group_id":-1007,"card_message_id":123,
                 "profile_keys":[[22,-1009]],"position":0}
        conn=SimpleNamespace(execute=AsyncMock())
        ctx=SimpleNamespace()
        ctx.bot=SimpleNamespace(send_message=AsyncMock())
        import contextlib
        @contextlib.asynccontextmanager
        async def acquired():
            yield conn
        mock_pool=SimpleNamespace(acquire=acquired)
        async def profile(uid,gid):
            return sender if uid==11 else recipient
        with patch.object(pv_matching,"get_session",AsyncMock(return_value=session)), \
             patch.object(pv_matching.db,"group_settings",AsyncMock(return_value={"requests":True})), \
             patch.object(handlers,"member",AsyncMock(return_value=True)), \
             patch.object(pv_matching.db,"get_profile",side_effect=profile), \
             patch.object(pv_matching.db,"send_request",AsyncMock(return_value={"id":17})), \
             patch.object(handlers,"group_label",AsyncMock(return_value="Group title")), \
             patch.object(handlers,"show_profile",AsyncMock(side_effect=[
                 SimpleNamespace(message_id=501),SimpleNamespace(message_id=502)])) as show, \
             patch.object(pv_matching,"pool",AsyncMock(return_value=mock_pool)), \
             patch.object(pv_matching.db,"remember_request_group_message",AsyncMock()) as remember, \
             patch.object(pv_matching,"set_position",AsyncMock()), \
             patch.object(pv_matching,"reset_timeout"):
            await pv_matching.confirm(update,ctx)
        self.assertEqual(show.await_count,2)
        self.assertEqual(show.await_args_list[0].args[1],-1007)
        self.assertEqual(show.await_args_list[0].args[2],recipient)
        self.assertEqual(show.await_args_list[1].args[1],-1009)
        self.assertEqual(show.await_args_list[1].args[2],sender)
        self.assertNotIn('tg://user?id=22',show.await_args_list[0].kwargs["header"])
        self.assertNotIn('tg://user?id=11',show.await_args_list[1].kwargs["header"])
        remember.assert_awaited_once_with(17,22,"card",502)

class SourceCardResultTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_result_updates_sender_group_without_exposing_recipient_account(self):
        from unittest.mock import patch
        sender={"display_name":"မောင်မောင်","bio":"","age":21,"location":None}
        recipient={"display_name":"စုစု","bio":"","age":20,"location":None}
        async def read_profile(uid,gid):
            return sender if uid==11 else recipient
        bot=SimpleNamespace(edit_message_caption=AsyncMock())
        req={"id":17,"sender_id":11,"recipient_id":22,
             "sender_group_id":-1007,"recipient_group_id":-1009,
             "sender_card_message_id":501}
        with patch.object(pv_matching.db,"get_profile",side_effect=read_profile), \
             patch.object(handlers,"group_label",AsyncMock(return_value="Card Club")):
            await pv_matching.update_sender_card_status(bot,req,"rejected")
        kws=bot.edit_message_caption.await_args.kwargs
        self.assertEqual(kws["chat_id"],-1007)
        self.assertEqual(kws["message_id"],501)
        self.assertIn("အဆင်မပြေခဲ့ဘူး",kws["caption"])
        self.assertNotIn("tg://user?id=22",kws["caption"])

class MainMenuReplyKeyboardTests(unittest.TestCase):
    def test_persistent_pv_home_menu_and_direct_search(self):
        key=pv_matching.MAIN_KEYBOARD
        labels=[b.text for row in key.keyboard for b in row]
        self.assertTrue(key.is_persistent)
        self.assertIn(pv_matching.MAIN_SEARCH,labels)
        self.assertIn(pv_matching.MAIN_INBOX,labels)
        self.assertIn(pv_matching.MAIN_PROFILE,labels)

    def test_source_group_lookup_requires_membership(self):
        code=(ROOT/"pv_matching.py").read_text(encoding="utf-8")
        self.assertIn("candidate_source_groups(uid)",code)
        self.assertIn("member(context.bot,gid,uid)",code)
        self.assertIn('callback_data=f"pvsource:{gid}"',code)

    def test_start_and_keyboard_routing(self):
        code=(ROOT/"handlers.py").read_text(encoding="utf-8")
        self.assertIn("reply_markup=pv_matching.MAIN_KEYBOARD",code)
        self.assertIn("private_keyboard_command",code)
        self.assertIn("pv_matching.source_callback",code)

class DirectSearchPickerTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_profile_does_not_browse(self):
        from unittest.mock import patch
        msg=SimpleNamespace(reply_text=AsyncMock())
        user=SimpleNamespace(id=11)
        update=SimpleNamespace(effective_chat=SimpleNamespace(type="private"),
            effective_user=user,effective_message=msg)
        with patch.object(pv_matching.db,"user_profiles",AsyncMock(return_value=[])), \
             patch.object(pv_matching,"get_session",AsyncMock(return_value=None)), \
             patch.object(pv_matching,"begin",AsyncMock()) as begin:
            await pv_matching.select_source_group(update,SimpleNamespace(bot=SimpleNamespace()))
        begin.assert_not_awaited()
        msg.reply_text.assert_awaited_once()
