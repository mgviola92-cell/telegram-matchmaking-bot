"""On-visit, opt-in PV request reminders; zero background jobs.

Reminders are not push notifications. They are emitted only after a user opens
PV /start, if a pending request expires within the next 4 hours and the user
has independently opted in. The database atomically prevents repeat digests
within 12 hours.
"""
from telegram import ReplyKeyboardMarkup
from telegram.error import TelegramError

import repository as db

MAIN_NOTIFY = "🔔 သတိပေးစာ"
ENABLE = "💌 စာသတိပေး ဖွင့်မယ်"
DISABLE = "🌷 စာသတိပေး ပိတ်မယ်"
HOME = "🏠 ပင်မ Menu"

MENU = ReplyKeyboardMarkup([[ENABLE, DISABLE], [HOME]],
                           resize_keyboard=True,is_persistent=True)


async def open_menu(update,context):
    """Only explicit private-menu access; never inject a group-wide keyboard."""
    import pv_matching
    if update.effective_chat.type!="private":
        return
    uid=update.effective_user.id
    own=await db.user_profiles(uid)
    if not own or not own[0]["adult_self_confirmed"]:
        await update.effective_message.reply_text(
            "🌷 Profile လေး အရင်ဖန်တီးပေးနော်။",
            reply_markup=pv_matching.MAIN_KEYBOARD)
        return
    pref=await db.get_notification_preference(uid)
    context.user_data["pv_notifications"]=True
    state="ဖွင့်ထားတယ်" if pref["expiring_inbox"] else "ပိတ်ထားတယ်"
    await update.effective_message.reply_text(
        f"🔔 စာသတိပေးချက်က အခု {state}နော်။\n"
        "💌 လာထားတဲ့ Request သက်တမ်းကုန်ဖို့ ၄ နာရီအတွင်း ရောက်နေတဲ့အခါ "
        "Bot PV ကို /start နဲ့ ပြန်ဖွင့်ရင် တစ်ခါတည်း အကျဉ်းချုပ်ပြပေးမယ်။\n"
        "🌷 ၁၂ နာရီအတွင်း ထပ်ခါထပ်ခါ မပို့ဘူး။ "
        "အလိုအလျောက် အချိန်မှန်ပို့တဲ့ Message မဟုတ်ဘူးနော်။",
        reply_markup=MENU)


async def handle(update,context):
    import pv_matching
    if update.effective_chat.type!="private" or not context.user_data.get("pv_notifications"):
        return False
    choice=update.effective_message.text
    if choice==HOME:
        context.user_data.pop("pv_notifications",None)
        await update.effective_message.reply_text(
            "💗 ပင်မ Menu ပြန်ရောက်ပြီနော်။",reply_markup=pv_matching.MAIN_KEYBOARD)
        return True
    if choice not in (ENABLE,DISABLE):
        return False
    saved=await db.set_notification_preference(update.effective_user.id,choice==ENABLE)
    context.user_data.pop("pv_notifications",None)
    await update.effective_message.reply_text(
        ("💌 စာသတိပေးချက် ဖွင့်ထားလိုက်ပြီနော်။" if choice==ENABLE else
         "🌷 စာသတိပေးချက် ပိတ်ထားလိုက်ပြီနော်။")
        if saved else "🌷 Profile အတည်ပြုချက် မရှိတော့ဘူးနော်။",
        reply_markup=pv_matching.MAIN_KEYBOARD)
    return True


async def maybe_expiring_digest(update,context):
    """One small DB check on ordinary PV /start; sends at most one summary."""
    if update.effective_chat.type!="private":
        return
    uid=update.effective_user.id
    count=await db.claim_expiring_inbox_digest(uid)
    if not count:
        return
    import pv_matching
    try:
        await update.effective_message.reply_text(
            f"💌 မင်းဆီ ရောက်ထားတဲ့ ဖိတ်ခေါ်စာ {count} စောင်က "
            "နောက် ၄ နာရီအတွင်း သက်တမ်းကုန်တော့မယ်နော်။ "
            "ဖြေချင်ရင် '💌 ရောက်လာတဲ့စာတွေ' ကို ဖွင့်ကြည့်နိုင်တယ်။",
            reply_markup=pv_matching.MAIN_KEYBOARD)
    except TelegramError:
        # Sending is best-effort. Avoid logging any private request content.
        return
