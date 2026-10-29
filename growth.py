"""Opt-in organic invitations and opaque global-profile sharing.

No new per-group profiles and no direct messages to uninvolved users.
"""
import secrets
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import repository as db

INTEREST_TAGS = (
    "🎵 သီချင်း", "🎮 Game", "🎬 ရုပ်ရှင်", "📚 စာအုပ်",
    "🎨 အနုပညာ", "🍳 အစားအသောက်", "🏞 ခရီးသွား", "🐈 တိရစ္ဆာန်",
    "⚽ အားကစား", "💻 နည်းပညာ",
)
INTEREST_FINISH = "🌷 ရွေးပြီးပြီ"
INTEREST_CLEAR = "🧹 အကုန်ရှင်းမယ်"
INTEREST_PICK = "🎨 ဝါသနာရွေးမယ်"
PROMPT_PICK = "💭 ကိုယ့်အကြောင်းပြောမယ်"
GLOBAL_SHARE = "💌 ကိုယ့်ကတ် မျှဝေမယ်"
INVITE_GROUP = "🌷 Group ထဲ ဖိတ်မယ်"


def interests_keyboard(selected=()):
    from telegram import ReplyKeyboardMarkup
    rows = [[INTEREST_TAGS[i], INTEREST_TAGS[i+1]] for i in range(0,len(INTEREST_TAGS),2)]
    rows += [[INTEREST_CLEAR,INTEREST_FINISH],["⬅️ နောက်ပြန်","🏠 ပင်မ Menu"]]
    return ReplyKeyboardMarkup(rows,resize_keyboard=True,is_persistent=True)


def invite_url(username):
    if not username or not username.replace("_","").isalnum():
        return None
    return f"https://t.me/{username}?startgroup=welcome"


def profile_start_url(username, token):
    if not username or not username.replace("_","").isalnum():
        return None
    return f"https://t.me/{username}?start=p_{token}"


async def group_invite(update, context):
    """User-selected add-to-group flow only; never mass invite."""
    if update.effective_chat.type!="private":
        await update.effective_message.reply_text("🌷 Group ဖိတ်စာလေးကို Bot Private မှာ ယူပေးနော်။")
        return
    username=(await context.bot.get_me()).username
    url=invite_url(username)
    if not url:
        await update.effective_message.reply_text("🌷 ဖိတ်စာလေး အခု မရသေးဘူးနော်။")
        return
    await update.effective_message.reply_text(
        "🌷 လူတောင်းပွဲကို ကိုယ်ကြိုက်တဲ့ Group ထဲ ဖိတ်နိုင်ပြီနော်။ Group Admin ရဲ့ ခွင့်ပြုချက်နဲ့ပဲ စတင်ပေးပါ။",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💗 Group ထဲ ဖိတ်မယ်",url=url)]]))


async def share_global_profile(update,context):
    """Share only one's own eligible global profile; Telegram share chooser is voluntary."""
    if update.effective_chat.type!="private":
        return
    uid=update.effective_user.id
    own=await db.user_profiles(uid)
    if not own or not own[0]["adult_self_confirmed"]:
        await update.effective_message.reply_text("🌷 Group မှာ Profile အရင်ဖန်တီးပြီးမှ မျှဝေလို့ရမယ်နော်။")
        return
    token=await db.get_or_create_profile_share_token(uid,secrets.token_urlsafe(24))
    if not token:
        await update.effective_message.reply_text("🌷 ဒီကတ်လေး မျှဝေလို့ မရသေးဘူးနော်။")
        return
    username=(await context.bot.get_me()).username
    url=profile_start_url(username,token)
    if not url:
        await update.effective_message.reply_text("🌷 Share Link လေး မရသေးဘူးနော်။")
        return
    share="https://t.me/share/url?url="+quote(url,safe="")+"&text="+quote("🎀 မိတ်ဆက်ကတ်လေး ကြည့်ကြည့်နော်",safe="")
    await update.effective_message.reply_text(
        "🎀 ကိုယ့် Global Profile လေးကို မိတ်ဆက်ပေးချင်တဲ့ Chat ထဲ ကိုယ်တိုင် မျှဝေနိုင်ပြီနော်။",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💌 Chat ထဲ မျှဝေမယ်",url=share)],
            [InlineKeyboardButton("🎀 ကိုယ့်ကတ် Link",url=url)]]))


async def show_shared_profile(update,context,token):
    """A share link never gives a stranger an account link or bypasses matching gates."""
    from handlers import member, show_profile, media_caption
    import pv_matching
    uid=update.effective_user.id
    if update.effective_chat.type!="private":
        return
    own=await db.user_profiles(uid)
    if not own or not own[0]["adult_self_confirmed"]:
        await update.effective_message.reply_text(
            "🌷 ဒီမိတ်ဆက်ကတ်ကို ကြည့်ဖို့ Group မှာ Profile အရင်ဖန်တီးထားဖို့ လိုတယ်နော်။",
            reply_markup=pv_matching.MAIN_KEYBOARD)
        return
    groups=await db.candidate_source_groups(uid)
    belongs=False
    for row in groups:
        gid=row["group_id"]
        settings=await db.group_settings(gid)
        if settings["matchmaking"] and await member(context.bot,gid,uid):
            belongs=True
            break
    if not belongs:
        await update.effective_message.reply_text(
            "🌷 Bot ရှိတဲ့ Group တစ်ခုထဲမှာ အဖွဲ့ဝင်ဖြစ်နေမှ ကတ်ကြည့်လို့ရမယ်နော်။",
            reply_markup=pv_matching.MAIN_KEYBOARD)
        return
    raw=await db.resolve_profile_share_token(token)
    if not raw:
        await update.effective_message.reply_text(
            "🌷 မိတ်ဆက်ကတ်လေး မရှိတော့ဘူးနော်။",
            reply_markup=pv_matching.MAIN_KEYBOARD)
        return
    target=await pv_matching.verified_target(context.bot,raw)
    if not target:
        await update.effective_message.reply_text(
            "🌷 အဲဒီကတ်လေး အခုဖွင့်လို့မရသေးဘူးနော်။",
            reply_markup=pv_matching.MAIN_KEYBOARD)
        return
    # No private-group name, @username, phone number, or pre-accept contact link.
    await show_profile(context.bot,uid,target,None,full_caption=media_caption(target))
    await update.effective_message.reply_text(
        "💗 မိတ်ဆက်ကတ်လေးပါ။ ဖူးစာရှာချင်ရင် ကိုယ့် Menu ကနေ ဆက်လှည့်ကြည့်နိုင်တယ်။",
        reply_markup=pv_matching.MAIN_KEYBOARD)
