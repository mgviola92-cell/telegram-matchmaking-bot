"""The match timer and cross-group mentions must keep their user-facing contract."""
import pathlib
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import handlers

ROOT = pathlib.Path(__file__).resolve().parents[1]


class MatchCardCopyTests(unittest.TestCase):
    def test_inactivity_is_three_minutes_everywhere(self):
        source = (ROOT / "handlers.py").read_text(encoding="utf-8")
        repo = (ROOT / "repository.py").read_text(encoding="utf-8")
        self.assertIn("seconds=180", source)
        self.assertIn("elapsed < 180", source)
        self.assertIn("seconds = 180 -", source)
        self.assertIn("interval '3 minutes'", repo)
        self.assertNotIn("interval '5 minutes'", repo)
        self.assertIn(">180", repo)

    def test_match_buttons_have_conversational_burmese(self):
        profile = {"user_id":22,"group_id":-1009}
        keyboard = handlers.match_buttons(11,-1007,profile,0,2)
        labels = " ".join(button.text for line in keyboard.inline_keyboard for button in line)
        self.assertNotIn("ဝိုင်းကျော်", labels)
        self.assertIn("မိတ်ဆက်ခွင့်", labels)
        self.assertNotIn("Group Only", labels)

    def test_request_card_shows_both_nicknames_and_group_names(self):
        msg=handlers.request_card_title(
            {"display_name":"မောင်မောင်"},{"display_name":"စုစု"},123,
            source_group="ဝိုင်း A",target_group="ဝိုင်း B")
        self.assertIn("မောင်မောင်",msg)
        self.assertIn("စုစု",msg)
        self.assertIn("ဝိုင်း A → ဝိုင်း B",msg)
        self.assertIn("#123",msg)
        self.assertNotIn("t.me/",msg)
        self.assertNotIn("@",msg)

    def test_request_names_escape_html(self):
        msg=handlers.request_card_title(
            {"display_name":"<sender>"},{"display_name":"S&U"},8)
        self.assertIn("&lt;sender&gt;",msg)
        self.assertIn("S&amp;U",msg)

    def test_account_mentions_are_clickable_nicknames(self):
        msg=handlers.request_card_title(
            {"display_name":"မောင်မောင်"},{"display_name":"စုစု"},123,
            sender_id=11,recipient_id=22,
            source_group="ဝိုင်း A",target_group="ဝိုင်း B")
        self.assertIn("မောင်မောင်",msg)
        self.assertNotIn('<a href="tg://user?id=11">',msg)
        self.assertIn('<a href="tg://user?id=22">စုစု</a>',msg)
        self.assertNotIn("@username",msg)
        self.assertNotIn("တောင်းဆိုသူ:",msg)
        self.assertNotIn("လက်ခံမယ့်သူ:",msg)

    def test_mobile_caption_separates_names_from_groups(self):
        card=handlers.request_card_title(
            {"display_name":"ပို့သူ"},{"display_name":"လက်ခံသူ"},34,
            source_group="Group A",target_group="Group B",sender_id=11,recipient_id=22)
        self.assertEqual(card.splitlines()[1],"")
        self.assertIn("🏡 Group - Group A → Group B",card.splitlines()[2])
        self.assertNotIn("tg://user?id=11",card)
        self.assertIn('href="tg://user?id=22"',card)

    def test_request_profile_does_not_repeat_sender_name(self):
        card = handlers.media_caption(
            {"display_name":"မောင်မောင်","bio":"ဟယ်လိုပါ"},
            "💌 မောင်မောင် က စုစု ကို လူတောင်းထားပြီ!\n")
        self.assertEqual(card.count("မောင်မောင်"),1)
        self.assertIn("ဟယ်လိုပါ",card)


class GroupLabelTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_group_has_clickable_group_title(self):
        bot=SimpleNamespace(get_chat=AsyncMock(
            return_value=SimpleNamespace(title="Anime Club",username="anime_club")))
        self.assertEqual(await handlers.group_label(bot,-1007),
            '<a href="https://t.me/anime_club">Anime Club</a>')

    async def test_match_caption_leo_summary_and_group_quote(self):
        bot=SimpleNamespace(get_chat=AsyncMock(
            return_value=SimpleNamespace(title="Card & Friends",username="card_friends")))
        profile={"display_name":"စုစု","age":21,"location":"Yangon",
                 "bio":"မင်္ဂလာပါ","group_id":-1007}
        title=await handlers.match_caption(bot,profile)
        self.assertIn("<b>စုစု</b>၊ 21၊ Yangon\n\n💬 မင်္ဂလာပါ",title)
        self.assertIn("မင်္ဂလာပါ\n\u200b\n\u200b\n<blockquote>",title)
        self.assertIn('<blockquote>🏡 Group - <a href="https://t.me/card_friends">Card &amp; Friends</a></blockquote>',title)

    async def test_long_mobile_bio_starts_in_own_paragraph(self):
        bot=SimpleNamespace(get_chat=AsyncMock(
            return_value=SimpleNamespace(title="Card",username=None)))
        bio="အကြောင်းအရာလေးတွေ " * 15
        text=await handlers.match_caption(bot,{
            "display_name":"ချစ်ချစ်","age":None,"location":None,
            "bio":bio,"group_id":-1007})
        self.assertTrue(text.startswith("<b>ချစ်ချစ်</b>\n\n💬 "))
        self.assertIn(bio,text)
        self.assertIn("\n\u200b\n\u200b\n<blockquote>",text)

    async def test_legacy_profile_omits_unknown_age_and_location(self):
        bot=SimpleNamespace(get_chat=AsyncMock(
            return_value=SimpleNamespace(title="Group B",username=None)))
        title=await handlers.match_caption(bot,{
            "display_name":"မောင်မောင်","age":None,"location":None,
            "bio":"", "group_id":-1007})
        self.assertIn("မောင်မောင်",title)
        self.assertNotIn("None",title)
        self.assertIn("<blockquote>🏡 Group - Group B</blockquote>",title)

    async def test_match_caption_has_group_without_repeating_bio(self):
        bot=SimpleNamespace(get_chat=AsyncMock(
            return_value=SimpleNamespace(title="Card Club",username=None)))
        profile={"display_name":"မောင်မောင်","bio":"မင်္ဂလာပါ",
                 "group_id":-1007}
        title=await handlers.match_caption(bot,profile)
        self.assertIn("Card Club",title)
        self.assertEqual(title.count("မင်္ဂလာပါ"),1)

    async def test_match_caption_escapes_private_group_title(self):
        bot=SimpleNamespace(get_chat=AsyncMock(
            return_value=SimpleNamespace(title="A&B Club",username=None)))
        title=await handlers.match_caption(bot,{"display_name":"မောင်မောင်","bio":"", "group_id":-1007})
        self.assertIn("A&amp;B Club",title)

    async def test_private_group_shows_title_without_invite_link(self):
        bot=SimpleNamespace(get_chat=AsyncMock(
            return_value=SimpleNamespace(title="Private Club",username=None)))
        self.assertEqual(await handlers.group_label(bot,-1007),"Private Club")
