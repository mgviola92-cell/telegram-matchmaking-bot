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
        keyboard = handlers.match_buttons(11,-1007,profile,0,2,False)
        labels = " ".join(button.text for line in keyboard.inline_keyboard for button in line)
        self.assertIn("ဝိုင်းကျော်", labels)
        self.assertIn("မိတ်ဆက်ခွင့်", labels)
        self.assertNotIn("Group Only", labels)

    def test_request_card_uses_recipient_username(self):
        msg = handlers.request_card_title(
            {"display_name":"မောင်မောင်"},{"display_name":"စုစု"},123,
            recipient_id=22,username="su_su")
        self.assertIn("https://t.me/su_su",msg)
        self.assertIn("@su_su",msg)
        self.assertIn("စုစု",msg)
        self.assertIn("#123",msg)

    def test_no_username_still_mentions_target_by_id(self):
        msg = handlers.request_card_title(
            {"display_name":"မောင်မောင်"},{"display_name":"စုစု"},123,
            recipient_id=22)
        self.assertIn('href="tg://user?id=22"',msg)
        self.assertNotIn("@None",msg)

    def test_names_are_html_escaped_and_username_is_safe(self):
        msg = handlers.request_card_title(
            {"display_name":"<sender>"},{"display_name":"S&U"},8,
            recipient_id=22,username="susu")
        self.assertIn("&lt;sender&gt;",msg)
        self.assertIn("S&amp;U",msg)
        self.assertIn("https://t.me/susu",msg)
        invalid = handlers.request_card_title(
            {"display_name":"A"},{"display_name":"B"},9,
            recipient_id=22,username="bad_link&bad")
        self.assertIn("tg://user?id=22",invalid)
        self.assertNotIn("https://t.me/bad",invalid)

    def test_request_profile_does_not_repeat_sender_name(self):
        card = handlers.media_caption(
            {"display_name":"မောင်မောင်","bio":"ဟယ်လိုပါ"},
            "💌 မောင်မောင် က စုစု ကို လူတောင်းထားပြီ!\n")
        self.assertEqual(card.count("မောင်မောင်"),1)
        self.assertIn("ဟယ်လိုပါ",card)


class MentionLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_username_returned(self):
        bot=SimpleNamespace(get_chat_member=AsyncMock(
            return_value=SimpleNamespace(user=SimpleNamespace(username="su_su"))))
        self.assertEqual(await handlers.request_recipient_username(bot,-1007,22),"su_su")

    async def test_missing_username_uses_id_mention(self):
        bot=SimpleNamespace(get_chat_member=AsyncMock(
            return_value=SimpleNamespace(user=SimpleNamespace(username=None))))
        self.assertIsNone(await handlers.request_recipient_username(bot,-1007,22))
