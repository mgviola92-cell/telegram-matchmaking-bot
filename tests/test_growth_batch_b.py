"""Offline checks for manual group growth events (no live Telegram accounts)."""
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.error import TelegramError
import conversation_starters
import group_events
import handlers
import repository

ROOT=pathlib.Path(__file__).resolve().parents[1]


def group_update(text="/question", gid=-100123):
    msg=SimpleNamespace(text=text,reply_text=AsyncMock())
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=81),
        effective_chat=SimpleNamespace(id=gid,type="supergroup"),
        effective_message=msg,message=msg,
    )


def callback_update(action="join",event_id=4,gid=-100123):
    answer=AsyncMock()
    q=SimpleNamespace(
        data=f"gevent:{action}:{event_id}",answer=answer,
        message=SimpleNamespace(chat=SimpleNamespace(id=gid,type="supergroup")),
        from_user=SimpleNamespace(id=81),
    )
    return SimpleNamespace(callback_query=q)


class GrowthBatchBContract(unittest.TestCase):
    def test_group_features_opt_in_default_off(self):
        self.assertIn("questions",repository.OPT_IN_GROUP_SETTINGS)
        self.assertIn("events",repository.OPT_IN_GROUP_SETTINGS)
        self.assertEqual(repository.OPT_IN_GROUP_SETTINGS,{"questions","events"})
        self.assertNotIn("public_browse",repository.SETTING_NAMES)
        self.assertIn("questions",handlers.SETTING_LABELS)
        self.assertIn("events",handlers.SETTING_LABELS)

    def test_global_profile_preserved(self):
        schema=(ROOT/"schema.sql").read_text(encoding="utf-8")
        self.assertIn("one_global_profile_per_user",schema)
        self.assertIn("REFERENCES profiles(user_id) ON DELETE CASCADE",schema)
        self.assertIn("local_day DATE",schema)
        self.assertIn("local_week DATE",schema)
        self.assertIn("Asia/Yangon",(ROOT/"repository.py").read_text(encoding="utf-8"))
        self.assertNotIn("profile_media_bytes",schema)

    def test_event_buttons_use_pv_only(self):
        board=group_events.event_buttons(9,"TestMatchBot",-100123)
        buttons=[b for row in board.inline_keyboard for b in row]
        self.assertEqual(buttons[0].callback_data,"gevent:join:9")
        self.assertEqual(buttons[1].callback_data,"gevent:leave:9")
        self.assertIn("?start=match_-100123",buttons[2].url)
        self.assertFalse(any("public_mode" in str(b) for b in buttons))

    def test_accepted_conversation_prompts_are_stable(self):
        prompt=conversation_starters.after_mutual_acceptance(62)
        self.assertIn("စကားစ",prompt)
        self.assertEqual(prompt,conversation_starters.after_mutual_acceptance(62))
        with self.assertRaises(ValueError):
            conversation_starters.after_mutual_acceptance(0)
        source=(ROOT/"handlers.py").read_text(encoding="utf-8")
        self.assertIn("after_mutual_acceptance(request_id)",source)

    def test_no_scheduled_jobs_or_media_files(self):
        source=(ROOT/"group_events.py").read_text(encoding="utf-8")
        self.assertNotIn("asyncio.sleep(",source)
        self.assertNotIn("download_file(",source)
        self.assertNotIn("send_photo(",source)
        self.assertNotIn("send_video(",source)


class GrowthBatchBFlows(unittest.IsolatedAsyncioTestCase):
    async def test_question_rejects_non_admin(self):
        u=group_update()
        bot=SimpleNamespace(send_message=AsyncMock())
        with patch("handlers.is_admin",AsyncMock(return_value=False)):
            await group_events.daily_question(u,SimpleNamespace(bot=bot))
        bot.send_message.assert_not_awaited()
        self.assertIn("Admin",u.message.reply_text.await_args.args[0])

    async def test_question_disabled_without_db_claim(self):
        u=group_update()
        ctx=SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        with patch("handlers.is_admin",AsyncMock(return_value=True)), \
             patch.object(group_events.db,"group_settings",
                         AsyncMock(return_value={"questions":False})), \
             patch.object(group_events.db,"claim_daily_question",AsyncMock()) as claim:
            await group_events.daily_question(u,ctx)
            claim.assert_not_awaited()

    async def test_question_posts_once_with_reserved_day(self):
        u=group_update()
        bot=SimpleNamespace(send_message=AsyncMock(
            return_value=SimpleNamespace(message_id=444)))
        ctx=SimpleNamespace(bot=bot)
        with patch("handlers.is_admin",AsyncMock(return_value=True)), \
             patch.object(group_events.db,"group_settings",
                          AsyncMock(return_value={"questions":True})), \
             patch.object(group_events.db,"claim_daily_question",
                          AsyncMock(return_value={"local_day":"2026-10-29"})), \
             patch.object(group_events.db,"question_posted",AsyncMock()) as posted:
            await group_events.daily_question(u,ctx)
        bot.send_message.assert_awaited_once()
        posted.assert_awaited_once_with(-100123,"2026-10-29",444)

    async def test_question_failed_send_does_not_consume_slot(self):
        u=group_update()
        bot=SimpleNamespace(send_message=AsyncMock(side_effect=TelegramError("failed")))
        ctx=SimpleNamespace(bot=bot)
        with patch("handlers.is_admin",AsyncMock(return_value=True)), \
             patch.object(group_events.db,"group_settings",
                          AsyncMock(return_value={"questions":True})), \
             patch.object(group_events.db,"claim_daily_question",
                          AsyncMock(return_value={"local_day":"2026-10-29"})), \
             patch.object(group_events.db,"release_daily_question",AsyncMock()) as release:
            await group_events.daily_question(u,ctx)
            release.assert_awaited_once_with(-100123,"2026-10-29")

    async def test_event_disabled_never_reserves(self):
        u=group_update("/event")
        bot=SimpleNamespace(send_message=AsyncMock())
        with patch("handlers.is_admin",AsyncMock(return_value=True)), \
             patch.object(group_events.db,"group_settings",
                          AsyncMock(return_value={"events":False})), \
             patch.object(group_events.db,"claim_weekly_event",AsyncMock()) as claim:
            await group_events.weekly_event(u,SimpleNamespace(bot=bot))
            claim.assert_not_awaited()
        bot.send_message.assert_not_awaited()

    async def test_event_success_posts_one_group_message(self):
        u=group_update("/event")
        bot=SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="TestMatchBot")),
                            send_message=AsyncMock(return_value=SimpleNamespace(message_id=111)))
        with patch("handlers.is_admin",AsyncMock(return_value=True)), \
             patch.object(group_events.db,"group_settings",
                          AsyncMock(return_value={"events":True})), \
             patch.object(group_events.db,"claim_weekly_event",
                          AsyncMock(return_value={"id":90})), \
             patch.object(group_events.db,"event_posted",AsyncMock()) as mark:
            await group_events.weekly_event(u,SimpleNamespace(bot=bot))
            mark.assert_awaited_once_with(90,-100123,111)
        bot.send_message.assert_awaited_once()

    async def test_event_button_denies_nonmember(self):
        u=callback_update()
        with patch("handlers.member",AsyncMock(return_value=False)), \
             patch.object(group_events.db,"update_event_participation",AsyncMock()) as change:
            await group_events.event_callback(u,SimpleNamespace(bot=SimpleNamespace()))
            change.assert_not_awaited()
        self.assertTrue(u.callback_query.answer.await_args.kwargs["show_alert"])

    async def test_event_button_denies_unconfirmed_user(self):
        u=callback_update()
        with patch("handlers.member",AsyncMock(return_value=True)), \
             patch.object(group_events.db,"user_profiles",
                          AsyncMock(return_value=[])), \
             patch.object(group_events.db,"update_event_participation",AsyncMock()) as change:
            await group_events.event_callback(u,SimpleNamespace(bot=SimpleNamespace()))
            change.assert_not_awaited()

    async def test_event_button_is_private_ack_not_new_group_post(self):
        u=callback_update()
        bot=SimpleNamespace(send_message=AsyncMock())
        with patch("handlers.member",AsyncMock(return_value=True)), \
             patch.object(group_events.db,"user_profiles",
                          AsyncMock(return_value=[{"adult_self_confirmed":True}])), \
             patch.object(group_events.db,"update_event_participation",
                          AsyncMock(return_value=5)) as update:
            await group_events.event_callback(u,SimpleNamespace(bot=bot))
            update.assert_awaited_once_with(4,-100123,81,True)
        bot.send_message.assert_not_awaited()
        self.assertIn("5",u.callback_query.answer.await_args.args[0])


if __name__=="__main__":
    unittest.main()
