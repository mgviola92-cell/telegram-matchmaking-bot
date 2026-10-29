"""Offline regression contracts for opt-in growth batch A."""
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import growth
import handlers
import pv_owner
import pv_profile
import repository

ROOT=pathlib.Path(__file__).resolve().parents[1]


def make_update(text=""):
    return SimpleNamespace(
        effective_chat=SimpleNamespace(type="private"),
        effective_user=SimpleNamespace(id=123),
        effective_message=SimpleNamespace(text=text,reply_text=AsyncMock()),
    )


class GrowthStaticContract(unittest.TestCase):
    def test_one_global_profile_not_group_only(self):
        schema=(ROOT/"schema.sql").read_text(encoding="utf-8")
        repo=(ROOT/"repository.py").read_text(encoding="utf-8")
        self.assertIn("one_global_profile_per_user",schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS profile_share_tokens",schema)
        self.assertIn("REFERENCES profiles(user_id) ON DELETE CASCADE",schema)
        self.assertIn("ON CONFLICT(user_id)",repo)
        self.assertNotIn("public_mode",repo)
        self.assertNotIn("public_browse",repo)

    def test_opaque_links_and_explicit_sharing(self):
        self.assertEqual(
            growth.invite_url("SampleBot"),
            "https://t.me/SampleBot?startgroup=welcome")
        link=growth.profile_start_url("SampleBot","AVeryLongOpaqueRandomToken")
        self.assertIn("?start=p_AVeryLongOpaqueRandomToken",link)
        self.assertNotIn("123456789",link)
        self.assertIsNone(growth.invite_url("bad/name"))

    def test_tags_are_limited(self):
        self.assertEqual(len(growth.INTEREST_TAGS),10)
        keyboard=growth.interests_keyboard()
        self.assertIn(growth.INTEREST_FINISH,str(keyboard))

    def test_caption_escapes_untrusted_prompt(self):
        data={"display_name":"<User>","age":None,"location":None,
              "bio":"hello", "interests":["🎵 သီချင်း"],
              "prompt_answer":"<contact>"}
        caption=handlers.caption(data)
        self.assertIn("&lt;User&gt;",caption)
        self.assertIn("&lt;contact&gt;",caption)
        self.assertNotIn("<contact>",caption)

    def test_no_background_cron_or_media_upload(self):
        source=(ROOT/"growth.py").read_text(encoding="utf-8")
        self.assertNotIn("download_file(",source)
        self.assertNotIn("send_document(",source)
        self.assertIn("secrets.token_urlsafe",source)


class GrowthFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_share_requires_existing_eligible_profile(self):
        u=make_update()
        ctx=SimpleNamespace()
        with patch.object(growth.db,"user_profiles",AsyncMock(return_value=[])), \
             patch.object(growth.db,"get_or_create_profile_share_token",AsyncMock()) as create:
            await growth.share_global_profile(u,ctx)
            create.assert_not_awaited()
        self.assertIn("Profile",u.effective_message.reply_text.await_args.args[0])

    async def test_share_user_can_choose_chat_no_raw_ids(self):
        u=make_update()
        bot=SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="SampleBot")))
        ctx=SimpleNamespace(bot=bot)
        with patch.object(growth.db,"user_profiles",AsyncMock(return_value=[{"adult_self_confirmed":True}])), \
             patch.object(growth.db,"get_or_create_profile_share_token",
                          AsyncMock(return_value="AVeryLongOpaqueRandomToken")):
            await growth.share_global_profile(u,ctx)
        markup=u.effective_message.reply_text.await_args.kwargs["reply_markup"]
        buttons=[b for row in markup.inline_keyboard for b in row]
        self.assertTrue(any("t.me/share/url?" in b.url for b in buttons))
        self.assertTrue(all("123" not in b.url for b in buttons))

    async def test_view_shared_link_rejects_nonmembers(self):
        u=make_update()
        ctx=SimpleNamespace(bot=SimpleNamespace())
        with patch.object(growth.db,"user_profiles",AsyncMock(
            return_value=[{"adult_self_confirmed":True}])), \
             patch.object(growth.db,"candidate_source_groups",AsyncMock(return_value=[])), \
             patch.object(growth.db,"resolve_profile_share_token",AsyncMock()) as lookup:
            await growth.show_shared_profile(u,ctx,"AVeryLongOpaqueRandomToken")
            lookup.assert_not_awaited()

    async def test_profile_prompt_rejects_multiline_input(self):
        with self.assertRaises(ValueError):
            await repository.save_profile_prompt(123,"Hello\nWorld")
        with self.assertRaises(ValueError):
            await repository.save_profile_prompt(123,"X"*121)

    async def test_interest_selection_is_canonical(self):
        u=make_update(growth.INTEREST_TAGS[0])
        state={"mode":"interests","group_id":-1001,"interests":[]}
        ctx=SimpleNamespace(user_data={"pv_profile":state})
        with patch.object(pv_profile.db,"get_profile",AsyncMock(return_value={
                "user_id":123,"group_id":-1001,"interests":[]})), \
             patch.object(pv_profile.db,"save_profile_interests",
                          AsyncMock(return_value={"user_id":123})) as save:
            self.assertTrue(await pv_profile.respond(u,ctx))
            self.assertEqual(state["interests"],[growth.INTEREST_TAGS[0]])
            self.assertTrue(await pv_profile.respond(make_update(growth.INTEREST_FINISH),ctx))
            save.assert_awaited_once_with(123,[growth.INTEREST_TAGS[0]])

    async def test_growth_dashboard_owner_only(self):
        u=make_update()
        ctx=SimpleNamespace()
        with patch("handlers.is_bot_owner",return_value=False), \
             patch.object(pv_owner.db,"owner_growth_summary",AsyncMock()) as summary:
            await pv_owner.growth_panel(u,ctx)
            summary.assert_not_awaited()

    async def test_growth_dashboard_is_aggregate(self):
        u=make_update()
        ctx=SimpleNamespace()
        counts={"profiles_total":44,"profiles_new_7d":9,"groups_observed":4,
                "requests_7d":15,"answered_7d":8}
        with patch("handlers.is_bot_owner",return_value=True), \
             patch.object(pv_owner.db,"owner_growth_summary",AsyncMock(return_value=counts)):
            await pv_owner.growth_panel(u,ctx)
        sent=u.effective_message.reply_text.await_args.args[0]
        self.assertIn("44",sent)
        self.assertNotIn("123",sent)


if __name__=="__main__":
    unittest.main()
