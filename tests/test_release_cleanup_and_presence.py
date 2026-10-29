"""Release tests for profile removal and live membership filtering."""
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import profile_cleanup
import pv_matching
import handlers

ROOT=pathlib.Path(__file__).resolve().parents[1]

class CleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_deletion_revokes_both_group_cards_intro_and_viewers(self):
        bot=SimpleNamespace(delete_message=AsyncMock(),send_message=AsyncMock())
        deleted={
            "affected_requests":[{"id":21,"sender_group_id":-101,
                "recipient_group_id":-102,"sender_card_message_id":300,
                "group_card_message_id":301,"group_prompt_message_id":302}],
            "affected":[{"sender_id":5,"recipient_id":6}],
            "intro_cards":[{"group_id":-102,"message_id":303}],
            "old_cards":[],
            "pv_cards":[{"user_id":8,"card_message_id":304}]}
        await profile_cleanup.cleanup_deleted_profile(bot,5,deleted,own_card_id=305)
        got={(x.kwargs["chat_id"],x.kwargs["message_id"])
             for x in bot.delete_message.await_args_list}
        self.assertEqual(got,{(-101,300),(-102,301),(-102,302),
                              (-102,303),(8,304),(5,305)})
        recipients={call.args[0] for call in bot.send_message.await_args_list}
        self.assertEqual(recipients,{6,8})

    async def test_failed_deletion_redacts_caption_and_revokes_button(self):
        from telegram.error import BadRequest
        bot=SimpleNamespace(delete_message=AsyncMock(
                side_effect=BadRequest("message cannot be deleted")),
            edit_message_caption=AsyncMock())
        result=await profile_cleanup.remove_card(bot,-101,300)
        self.assertFalse(result)
        self.assertIsNone(bot.edit_message_caption.await_args.kwargs["reply_markup"])

class MembershipTests(unittest.IsolatedAsyncioTestCase):
    async def test_departed_user_not_shown(self):
        item={"user_id":9,"group_id":-102}
        with patch.object(handlers,"member",AsyncMock(return_value=False)), \
             patch.object(pv_matching.db,"get_profile",AsyncMock()) as get:
            result=await pv_matching.verified_target(SimpleNamespace(),item)
        self.assertIsNone(result)
        get.assert_not_awaited()

    async def test_group_disabled_not_shown(self):
        item={"user_id":9,"group_id":-102}
        with patch.object(handlers,"member",AsyncMock(return_value=True)), \
             patch.object(pv_matching.db,"group_settings",AsyncMock(
                 return_value={"matchmaking":False,"requests":True})):
            result=await pv_matching.verified_target(SimpleNamespace(),item)
        self.assertIsNone(result)

    def test_only_present_group_profiles_enter_candidate_pool(self):
        code=(ROOT/"repository.py").read_text(encoding="utf-8")
        section=code.split("async def browse_profiles",1)[1].split(
            "async def send_request",1)[0]
        self.assertIn("JOIN LATERAL",section)
        self.assertNotIn("COALESCE(venue.group_id,p.group_id)",section)

class CleanupSqlTests(unittest.TestCase):
    def test_global_profile_cleanup_returns_every_reference(self):
        code=(ROOT/"repository.py").read_text(encoding="utf-8")
        section=code.split("async def delete_profile",1)[1].split(
            "async def remember_intro_message",1)[0]
        for field in ("sender_card_message_id","group_card_message_id",
                      "group_prompt_message_id","pv_match_sessions",
                      "profile_intro_messages","viewed_profiles"):
            self.assertIn(field,section)
        self.assertIn("DELETE FROM requests",section)
