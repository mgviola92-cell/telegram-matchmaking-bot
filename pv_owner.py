"""Owner-only PV ReplyKeyboard operations for the isolated QA group."""
import logging
from telegram import ReplyKeyboardMarkup
from telegram.error import TelegramError
import repository as db
import pv_matching

RESET="♻️ Test Request Reset"
CONFIRM="✅ Test Requests Reset"
CANCEL="🌷 မလုပ်တော့ဘူး"
CHANGE="⚙️ Test Group ပြောင်းမယ်"
REFRESH="🔄 Panel ပြန်ကြည့်မယ်"
HOME="🏠 ပင်မ Menu"
MENU=ReplyKeyboardMarkup([[RESET,CHANGE],[REFRESH,HOME]],
    resize_keyboard=True,is_persistent=True)
CONFIRM_MENU=ReplyKeyboardMarkup([[CONFIRM,CANCEL],[HOME]],
    resize_keyboard=True,is_persistent=True)
GROUP_MENU=ReplyKeyboardMarkup([[CANCEL]],
    resize_keyboard=True,is_persistent=True)

async def open_panel(update,context):
    from handlers import is_bot_owner,OWNER_GROUP_INPUT
    if not is_bot_owner(update) or update.effective_chat.type!="private":
        return -1
    gid=await db.get_owner_qa_group(update.effective_user.id)
    if not gid:
        await update.effective_message.reply_text(
            "🧪 Test Group ID (-100...) ကို ရိုက်ပေးနော်။",
            reply_markup=GROUP_MENU)
        return OWNER_GROUP_INPUT
    count=await db.owner_test_request_count(update.effective_user.id,gid)
    await update.effective_message.reply_text(
        f"🧪 Owner QA Panel\nTest Group: {gid}\nTest Requests: {count}",
        reply_markup=MENU)
    return -1


async def change_group(update,context):
    from handlers import is_bot_owner,OWNER_GROUP_INPUT
    if not is_bot_owner(update) or update.effective_chat.type!="private":
        return -1
    await update.effective_message.reply_text(
        "🧪 Test Group ID (-100...) ကို ရိုက်ပေးနော်။",
        reply_markup=GROUP_MENU)
    return OWNER_GROUP_INPUT


async def handle(update,context):
    from handlers import is_bot_owner
    if update.effective_chat.type!="private" or not is_bot_owner(update):
        return False
    uid=update.effective_user.id
    text=update.effective_message.text
    if text==HOME:
        context.user_data.pop("pv_owner_pending",None)
        await update.effective_message.reply_text(
            "💗 ပင်မ Menu ကို ပြန်ရောက်ပြီနော်။",
            reply_markup=pv_matching.MAIN_KEYBOARD)
        return True
    if text in (CANCEL,REFRESH):
        context.user_data.pop("pv_owner_pending",None)
        await open_panel(update,context)
        return True
    gid=await db.get_owner_qa_group(uid)
    if not gid:
        await update.effective_message.reply_text(
            "🧪 Test Group ကို အရင်သတ်မှတ်ပေးနော်။",
            reply_markup=GROUP_MENU)
        return True
    if text==RESET:
        context.user_data["pv_owner_pending"]=gid
        count=await db.owner_test_request_count(uid,gid)
        await update.effective_message.reply_text(
            f"⚠️ သတ်မှတ်ထားတဲ့ Test Group ထဲက Request {count} ခုကို Reset လုပ်မလား?",
            reply_markup=CONFIRM_MENU)
        return True
    if text==CONFIRM:
        if context.user_data.pop("pv_owner_pending",None)!=gid:
            await update.effective_message.reply_text(
                "🌷 အတည်ပြုချက် မရှိတော့ဘူးနော်။",reply_markup=MENU)
            return True
        rows=await db.reset_owner_test_requests(uid,gid)
        for item in rows:
            for field in ("group_card_message_id","group_prompt_message_id",
                          "sender_card_message_id"):
                mid=item.get(field)
                if not mid:
                    continue
                try:
                    await context.bot.delete_message(chat_id=gid,message_id=mid)
                except TelegramError:
                    try:
                        await context.bot.edit_message_reply_markup(
                            chat_id=gid,message_id=mid,reply_markup=None)
                    except TelegramError:
                        logging.info("Owner test request message could not be revoked")
        await update.effective_message.reply_text(
            f"✅ Test Request {len(rows)} ခု Reset ပြီးပြီနော်။",
            reply_markup=MENU)
        return True
    return False
