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

    async def test_private_group_shows_title_without_invite_link(self):
        bot=SimpleNamespace(get_chat=AsyncMock(
            return_value=SimpleNamespace(title="Private Club",username=None)))
        self.assertEqual(await handlers.group_label(bot,-1007),"Private Club")
