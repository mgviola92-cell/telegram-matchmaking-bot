"""Opt-in, admin-started group activities (no scheduler or media downloads)."""
import logging
import secrets

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup
from telegram.error import TelegramError

import repository as db

# Fixed, original, community-safe prompts; no generative API and no personal data.
QUESTIONS = (
    "🎵 အကြိုက်ဆုံး သီချင်းတစ်ပုဒ် ပြောပြမလား?",
    "🎬 အကြိုက်ဆုံး ရုပ်ရှင်တစ်ကား ရှိလား?",
    "🌿 စိတ်အေးချမ်းစေတဲ့ နေရာမျိုးဆို ဘယ်လိုနေရာလေးလဲ?",
    "🍜 အမြဲစားချင်နေတတ်တဲ့ ဟင်းတစ်မျိုးက ဘာလဲ?",
    "🎮 အဖွဲ့လိုက် ဆော့ရင် ပိုပျော်မယ့် Game က ဘာဖြစ်မလဲ?",
    "📚 အကြိုက်ဆုံး စာအုပ် ဒါမှမဟုတ် ဇာတ်လမ်းလေး ရှိလား?",
    "🐾 ချစ်စရာ တိရစ္ဆာန်လေးတွေထဲ ဘယ်ကောင်ကို ကြိုက်လဲ?",
    "☀️ အားလပ်ရက်မှာ လုပ်ချင်ဆုံးအရာလေးက ဘာလဲ?",
    "🎨 သင်ယူချင်နေတဲ့ ဝါသနာအသစ်လေး ရှိလား?",
    "🍰 ချိုချိုလေးနဲ့ စပ်စပ်လေး ဘယ်ဘက်ကို ပိုကြိုက်လဲ?",
)

EVENT_TITLE = "🌷 အပတ်စဉ် ဖူးစာမိတ်ဆက်ပွဲ"
JOIN = "💕 ဒီပွဲလေး ပါမယ်"
LEAVE = "🌷 ဒီပွဲတော့ နားမယ်"


def event_buttons(event_id, bot_username, group_id):
    # Telegram selects the group in an explicit, existing PV-only match flow.
    url=f"https://t.me/{bot_username}?start=match_{group_id}"
    return InlineKeyboardMarkup([
        [Button(JOIN,callback_data=f"gevent:join:{event_id}"),
         Button(LEAVE,callback_data=f"gevent:leave:{event_id}")],
        [Button("🎀 Private မှာ ဆုံမယ်",url=url)],
    ])


async def daily_question(update,context):
    """Admins manually post no more than one question per local day."""
    from handlers import is_admin
    if update.effective_chat.type not in ("group","supergroup"):
        return
    gid=update.effective_chat.id
    if not await is_admin(context.bot,gid,update.effective_user.id):
        await update.effective_message.reply_text("🌷 ဒီမေးခွန်းပွဲလေးကို Group Admin ကပဲ စနိုင်တာနော်။")
        return
    opts=await db.group_settings(gid)
    if not opts["questions"]:
        await update.effective_message.reply_text(
            "🌷 ဒီ Group မှာ မေးခွန်းပွဲ မဖွင့်ရသေးဘူးနော်။ Admin /settings ကနေ ဖွင့်ပေးပါ။")
        return
    # Pick among prompts not used in the last nine eligible group days.
    # One tiny read per admin command; never a scheduled database poll.
    recent=await db.recent_daily_question_ids(gid,limit=len(QUESTIONS)-1)
    choices=[i for i in range(len(QUESTIONS)) if i not in recent]
    prompt_id=secrets.choice(choices) if choices else secrets.randbelow(len(QUESTIONS))
    slot=await db.claim_daily_question(gid,prompt_id)
    if slot is None:
        await update.effective_message.reply_text(
            "🎀 ဒီနေ့ရဲ့ မေးခွန်းလေး တင်ပြီးသားနော်။ နောက်နေ့မှ တစ်ခုထပ်ဖွင့်ကြမယ်။")
        return
    try:
        sent=await context.bot.send_message(
            chat_id=gid,
            text="🌻 <b>ဒီနေ့ရဲ့ စကားဝိုင်းလေး</b>\n\n"
                 + QUESTIONS[prompt_id]
                 + "\n\n💕 စိတ်ပါရင် Group ထဲမှာ ပြောပြခဲ့နော်။",
            parse_mode="HTML",disable_notification=True)
        await db.question_posted(gid,slot["local_day"],sent.message_id)
    except TelegramError:
        logging.exception("Daily group question could not be posted")
        await db.release_daily_question(gid,slot["local_day"])


async def weekly_event(update,context):
    """Only admins create a voluntary 18+ weekly invitation, without auto matching."""
    from handlers import is_admin
    if update.effective_chat.type not in ("group","supergroup"):
        return
    gid=update.effective_chat.id
    if not await is_admin(context.bot,gid,update.effective_user.id):
        await update.effective_message.reply_text("🌷 ဒီပွဲလေးကို Group Admin ကပဲ စနိုင်တာနော်။")
        return
    opts=await db.group_settings(gid)
    if not opts["events"]:
        await update.effective_message.reply_text(
            "🌷 ဒီ Group မှာ အပတ်စဉ်ပွဲလေး မဖွင့်ရသေးဘူးနော်။ /settings မှာ ဖွင့်ပေးပါ။")
        return
    row=await db.claim_weekly_event(gid)
    if row is None:
        await update.effective_message.reply_text(
            "🎀 ဒီအပတ် မိတ်ဆက်ပွဲလေး ဖွင့်ပြီးသားနော်။ နောက်အပတ်မှ ပွဲအသစ်လုပ်ကြမယ်။")
        return
    try:
        username=(await context.bot.get_me()).username
        if not username:
            raise TelegramError("Bot username unavailable")
        sent=await context.bot.send_message(
            gid,
            f"<b>{EVENT_TITLE}</b>\n\n"
            "💌 အသက် ၁၈ နှစ်ပြည့်ပြီး ပါဝင်ချင်သူတွေပဲ ကိုယ်တိုင် ခလုတ်နှိပ်ပါနော်။\n"
            "🎀 ပါဝင်ထားသူတွေရဲ့ နာမည်နဲ့ Contact ကို Group ထဲ အလိုအလျောက် မဖော်ပြပါဘူး။\n"
            "💕 ဆုံချင်ရင် Bot Private မှာ Profile လှည့်ကြည့်နိုင်တယ်။",
            parse_mode="HTML",disable_notification=True,
            reply_markup=event_buttons(row["id"],username,gid))
        await db.event_posted(row["id"],gid,sent.message_id)
    except TelegramError:
        logging.exception("Weekly event invitation could not be posted")
        await db.release_weekly_event(row["id"],gid)


async def event_callback(update,context):
    """Validate group/event/user again and only send private callback acknowledgement."""
    from handlers import member
    q=update.callback_query
    try:
        _, action, raw_id=q.data.split(":")
        event_id=int(raw_id)
    except (ValueError,TypeError,AttributeError):
        await q.answer("🌷 ဒီပွဲခလုတ်လေး အဆင်မပြေတော့ဘူးနော်။",show_alert=True)
        return
    if action not in ("join","leave") or event_id<=0 or q.message.chat.type not in ("group","supergroup"):
        await q.answer("🌷 ဒီပွဲခလုတ်လေး အဆင်မပြေတော့ဘူးနော်။",show_alert=True)
        return
    gid=q.message.chat.id
    uid=q.from_user.id
    if not await member(context.bot,gid,uid):
        await q.answer("🌷 ဒီ Group မှာ အဖွဲ့ဝင်ဖြစ်နေမှ ပွဲဝင်လို့ရမယ်နော်။",show_alert=True)
        return
    own=await db.user_profiles(uid)
    if not own or not own[0]["adult_self_confirmed"]:
        await q.answer("💗 Profile နဲ့ အသက် ၁၈ ပြည့်ကြောင်း အရင်အတည်ပြုပေးနော်။",show_alert=True)
        return
    count=await db.update_event_participation(event_id,gid,uid,action=="join")
    if count is None:
        await q.answer("🌷 ဒီအပတ်ပွဲလေး ပိတ်သွားပြီနော်။",show_alert=True)
        return
    await q.answer(
        f"💕 ဒီပွဲလေးမှာ ပါဝင်လိုက်ပြီနော်။ ပါဝင်သူ {count} ယောက် ရှိပြီ။" if action=="join" else
        f"🌷 ဒီပွဲကနေ ထွက်လိုက်ပြီနော်။ ပါဝင်သူ {count} ယောက် ရှိတယ်။")
