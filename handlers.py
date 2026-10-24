"""Group-specific registration and browsing handlers. No background database polling."""
import asyncio
from datetime import datetime, timezone
import html
import json
import logging
import os
from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, InputMediaPhoto, InputMediaVideo
from telegram.error import TelegramError
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, ChatMemberHandler, filters, ConversationHandler
import repository as db
from responses import say

CONFIRM_AGE, NAME, AGE, MEDIA, BIO = range(5)
EDIT_TEXT, EDIT_MEDIA = range(5, 7)
REJECTION_TEXT = 7
drafts = {}
_browse_timer_tasks = {}

async def _expire_browse(bot, uid, gid, message_id, delay):
    try:
        await asyncio.sleep(max(0, delay))
        session = await db.get_browse_session(uid,gid)
        if not session or session['message_id'] != message_id:
            return
        elapsed = (datetime.now(timezone.utc)-session['updated_at']).total_seconds()
        if elapsed < 180:
            # Re-check once after the exact three-minute inactivity deadline.
            await asyncio.sleep(180 - elapsed + 0.1)
            session = await db.get_browse_session(uid,gid)
            if not session or session['message_id'] != message_id:
                return
            if (datetime.now(timezone.utc)-session['updated_at']).total_seconds() < 180:
                return
        settings = await db.group_settings(gid)
        if not settings["cleanup"]:
            return
        try:
            await bot.edit_message_reply_markup(chat_id=gid,message_id=message_id,reply_markup=None)
        except TelegramError:
            logging.info('Browse card timeout: markup unavailable')
    except asyncio.CancelledError:
        return
    except Exception:
        logging.exception('Browse timeout could not finish')
    finally:
        key = (uid,gid)
        if _browse_timer_tasks.get(key) is asyncio.current_task():
            _browse_timer_tasks.pop(key,None)

def schedule_browse_timeout(bot,uid,gid,message_id,seconds=180):
    key = (uid,gid)
    old = _browse_timer_tasks.pop(key,None)
    if old and not old.done():
        old.cancel()
    _browse_timer_tasks[key] = asyncio.create_task(_expire_browse(bot,uid,gid,message_id,seconds))

async def restore_browse_timeouts(bot):
    for item in await db.recent_browse_sessions():
        seconds = 180 - (datetime.now(timezone.utc)-item['updated_at']).total_seconds()
        schedule_browse_timeout(bot,item['viewer_id'],item['group_id'],item['message_id'],seconds)

async def shutdown_browse_timeouts():
    tasks = list(_browse_timer_tasks.values())
    _browse_timer_tasks.clear()
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks,return_exceptions=True)

def caption(p):
    return f"💗 <b>{html.escape(p['display_name'])}</b>\n\n{html.escape(p['bio'] or 'စကားလေးတွေ ပြောကြည့်ရအောင် 💌')}"

async def member(bot, group_id, user_id):
    try:
        m = await bot.get_chat_member(group_id, user_id)
        if m.status == "restricted":
            return bool(m.is_member)
        return m.status in ("member", "administrator", "creator")
    except TelegramError:
        return False

OWNER_GROUP_INPUT = 8

def owner_config():
    """A trusted owner must be preconfigured; first-visitor claim is unsafe."""
    from owner_identity import OWNER_TELEGRAM_ID
    try:
        return int(OWNER_TELEGRAM_ID or os.getenv("OWNER_ID", "0")), 0
    except (TypeError, ValueError):
        return 0, 0

def is_bot_owner(update):
    owner_id, _ = owner_config()
    user = update.effective_user
    return bool(owner_id and user and user.id == owner_id)

async def owner_panel(update, context):
    """A private-only owner panel. Others get no messages and no error replies."""
    if not is_bot_owner(update) or update.effective_chat.type != "private":
        return ConversationHandler.END
    group_id = await db.get_owner_qa_group(update.effective_user.id)
    if not group_id:
        await update.effective_message.reply_text(
            "🧪 <b>Owner QA Setup</b>\n"
            "ဒီတစ်ခါပဲ Test Group ID လေး ထည့်ပေးပါ။\n"
            "Group ID က -100 နဲ့ စတဲ့ Telegram Numeric ID ဖြစ်ရမယ်။\n"
            "/cancel နဲ့ ပြန်ထွက်နိုင်ပါတယ်။",
            parse_mode="HTML")
        return OWNER_GROUP_INPUT
    count = await db.owner_test_request_count(update.effective_user.id,group_id)
    await update.effective_message.reply_text(
        f"🧪 <b>Owner QA Panel</b>\nTest Group: <code>{group_id}</code>\n"
        f"ကိုယ်ပို့ထားသော Test Request: <b>{count}</b> ခု\n"
        "Reset လုပ်ပြီးရင် လက်ခံသူက Request အသစ်ကို ပြန်ဖြေနိုင်ပါတယ်။",
        parse_mode="HTML",
        reply_markup=K([[B("♻️ Test Request Reset",callback_data="owner:ask_reset")],
                        [B("⚙️ Test Group ပြောင်းမယ်",callback_data="owner:enter_group")],
                        [B("🔄 ပြန်စစ်မယ်",callback_data="owner:refresh")]]))
    return ConversationHandler.END

async def owner_change_group(update, context):
    q = update.callback_query
    if not is_bot_owner(update) or q.message.chat.type != "private":
        return ConversationHandler.END
    await q.answer()
    await q.edit_message_text(
        "🧪 Test Group ID အသစ်ကို ရိုက်ထည့်ပေးပါ။\n"
        "ဥပမာ: -1001234567890\n/cancel နဲ့ ပြန်ထွက်နိုင်တယ်။")
    return OWNER_GROUP_INPUT

async def owner_group_input(update, context):
    if not is_bot_owner(update) or update.effective_chat.type != "private":
        return ConversationHandler.END
    value = update.message.text.strip()
    try:
        group_id = int(value)
    except ValueError:
        await update.message.reply_text("🌷 Group ID ကို ဂဏန်းနဲ့ပဲ ထည့်ပေးနော်။")
        return OWNER_GROUP_INPUT
    if group_id >= 0 or not str(group_id).startswith("-100"):
        await update.message.reply_text("🌷 Telegram Supergroup ID (-100...) ကို ထည့်ပေးနော်။")
        return OWNER_GROUP_INPUT
    try:
        member_info = await context.bot.get_chat_member(group_id,update.effective_user.id)
        bot_info = await context.bot.get_me()
        bot_member = await context.bot.get_chat_member(group_id,bot_info.id)
    except TelegramError:
        await update.message.reply_text(
            "🌷 ဒီ Group ကို Bot က မဖတ်နိုင်သေးဘူး။ Bot ကို Group ထဲထည့်ပြီး ပြန်စမ်းပေးနော်။")
        return OWNER_GROUP_INPUT
    if member_info.status not in ("administrator","creator") or bot_member.status not in ("member","administrator","creator"):
        await update.message.reply_text(
            "🌷 Test Group ရဲ့ Admin ဖြစ်ရမယ်၊ Bot လည်း Group ထဲရှိရမယ်နော်။")
        return OWNER_GROUP_INPUT
    await db.set_owner_qa_group(update.effective_user.id,group_id)
    await update.message.reply_text(
        f"✅ Test Group <code>{group_id}</code> ကို သိမ်းထားပြီးပြီ။\n"
        "နောက်တစ်ကြိမ် /owner ဖွင့်ရင် ထပ်မမေးတော့ဘူး။",
        parse_mode="HTML")
    return ConversationHandler.END

async def owner_group_cancel(update, context):
    if is_bot_owner(update) and update.effective_chat.type == "private":
        await update.message.reply_text("🌷 Owner Setup ကို ရပ်ထားလိုက်ပြီ။")
    return ConversationHandler.END

async def owner_callback(update, context):
    q = update.callback_query
    if not is_bot_owner(update) or q.message.chat.type != "private":
        return
    owner_id = q.from_user.id
    group_id = await db.get_owner_qa_group(owner_id)
    if not group_id:
        return
    action = q.data.split(":",1)[1]
    if action == "ask_reset":
        count = await db.owner_test_request_count(owner_id,group_id)
        await q.answer()
        await q.edit_message_text(
            f"🧪 Test Group <code>{group_id}</code> ထဲမှာ ကိုယ်ပို့ထားတဲ့ Request "
            f"<b>{count}</b> ခုကို Reset လုပ်မလား?\n"
            "လက်ခံ/ငြင်းခဲ့တဲ့ Request တွေပါ Reset လုပ်ပြီး "
            "Request အသစ်ကို လက်ခံသူက ထပ်ဖြေနိုင်ပါမယ်။",
            parse_mode="HTML",
            reply_markup=K([[B("✅ Test Request များ Reset",callback_data="owner:reset")],
                            [B("↩️ မလုပ်တော့ဘူး",callback_data="owner:refresh")]]))
        return
    if action == "reset":
        rows = await db.reset_owner_test_requests(owner_id,group_id)
        for request in rows:
            for key in ("group_card_message_id","group_prompt_message_id"):
                message_id = request[key]
                if message_id:
                    try:
                        await context.bot.delete_message(group_id,message_id)
                    except TelegramError:
                        try:
                            await context.bot.edit_message_reply_markup(
                                chat_id=group_id,message_id=message_id,reply_markup=None)
                        except TelegramError:
                            logging.info("Test group request message could not be cleaned")
        await q.answer("Reset ပြီးပြီ")
        await q.edit_message_text(
            f"✅ Test Request {len(rows)} ခု Reset လုပ်ပြီးပြီ။\n"
            "ဖိတ်ခေါ်စာ အသစ်ပြန်ပို့ပြီး လက်ခံ/ငြင်းတာကို ထပ်စမ်းလို့ရပြီ။",
            reply_markup=K([[B("🔄 Owner Panel",callback_data="owner:refresh")]]))
        return
    if action == "refresh":
        count = await db.owner_test_request_count(owner_id,group_id)
        await q.answer()
        await q.edit_message_text(
            f"🧪 <b>Owner QA Panel</b>\nTest Group: <code>{group_id}</code>\n"
            f"ကိုယ်ပို့ထားသော Test Request: <b>{count}</b> ခု",
            parse_mode="HTML",
            reply_markup=K([[B("♻️ Test Request Reset",callback_data="owner:ask_reset")],
                            [B("⚙️ Test Group ပြောင်းမယ်",callback_data="owner:enter_group")]]))

def private_menu():
    """Telegram-native inline navigation; no web app."""
    return K([
        [B("🎀 ကိုယ့်မိတ်ဆက်ကတ်တွေ", callback_data="home:profile")],
        [B("💌 ရောက်လာတဲ့စာတွေ", callback_data="home:inbox"),
         B("📮 ပို့ထားတဲ့စာတွေ", callback_data="home:outgoing")],
        [B("🌷 စတင်အသုံးပြုပုံ", callback_data="home:help")],
    ])

async def show_menu_page(q, text, keyboard):
    """Replace one inline page, not a new chat bubble."""
    if q.message.photo or q.message.video:
        # Switching media -> text requires replacing the message type.
        # Publish the new menu only after successfully removing the old card.
        try:
            await q.message.delete()
        except TelegramError:
            logging.warning("Cannot remove old media menu; aborting navigation")
            return
        await q.message.chat.send_message(text, reply_markup=keyboard)
    else:
        try:
            await q.edit_message_text(text, reply_markup=keyboard)
        except TelegramError as exc:
            if "message is not modified" not in str(exc).lower():
                raise

async def home_callback(update, context):
    q = update.callback_query
    if q.message.chat.type != "private":
        await q.answer("ဒီမီနူးလေးက Private Chat အတွက်ပါ။", show_alert=True)
        return
    action = q.data.split(":",1)[1]
    await q.answer()
    if action == "profile":
        rows = await db.user_profiles(q.from_user.id)
        if not rows:
            await show_menu_page(q,
                "🌷 မိတ်ဆက်ကတ် မရှိသေးဘူးနော်။ Group ထဲမှာ /register နဲ့ စတင်နိုင်တယ်။",
                K([[B("💗 ပင်မစာမျက်နှာ",callback_data="home:main")]]))
            return
        buttons = [[B(("🌍 " if p["is_public"] else "💗 ") + p["display_name"][:25],
                      callback_data=f"profile_view:{p['group_id']}")] for p in rows]
        buttons.append([B("💗 ပင်မစာမျက်နှာ", callback_data="home:main")])
        await show_menu_page(q,"🎀 ကိုယ့်မိတ်ဆက်ကတ်လေး ရွေးကြည့်မယ်နော်။",K(buttons))
    elif action == "inbox":
        rows = await db.incoming_requests(q.from_user.id)
        if not rows:
            await show_menu_page(q,say("inbox_empty",q.from_user.id),
                                 K([[B("💗 ပင်မစာမျက်နှာ",callback_data="home:main")]]))
            return
        buttons = []
        for item in rows[:30]:
            sender = await db.get_profile(item["sender_id"],item["sender_group_id"])
            if sender:
                buttons.append([B("💌 "+sender["display_name"][:25],
                                  callback_data=f"inbox_open:{item['id']}")])
        buttons.append([B("💗 ပင်မစာမျက်နှာ",callback_data="home:main")])
        await show_menu_page(q,"💌 ရောက်လာတဲ့စာတွေထဲက ဖွင့်ကြည့်ချင်တာ ရွေးနော်။",K(buttons))
    elif action == "outgoing":
        rows = await db.outgoing_requests(q.from_user.id)
        if not rows:
            await show_menu_page(q,say("outgoing_empty",q.from_user.id),
                                 K([[B("💗 ပင်မစာမျက်နှာ",callback_data="home:main")]]))
            return
        buttons = []
        for item in rows[:30]:
            target = await db.get_profile(item["recipient_id"],item["recipient_group_id"])
            if target:
                buttons.append([B("📮 "+target["display_name"][:25]+" · ပြန်ရုပ်သိမ်းမယ်",
                                  callback_data=f"withdraw_ask:{item['id']}")])
        buttons.append([B("💗 ပင်မစာမျက်နှာ",callback_data="home:main")])
        await show_menu_page(q,"📮 ကိုယ်ပို့ထားတဲ့ စာလေးတွေကို ဒီမှာ စီမံနိုင်တယ်။",K(buttons))
    elif action == "help":
        await show_menu_page(q,
            "🌷 Group ထဲမှာ /register နဲ့ စာရင်းသွင်းနိုင်တယ်။\n"
            "🎀 စာရင်းသွင်းပြီးရင် /profile နဲ့ ကတ်လေးကို စီမံနိုင်တယ်။\n"
            "💌 Group ထဲမှာ /match နဲ့ ကတ်လေးတွေ ကြည့်နိုင်တယ်။",
            K([[B("💗 ပင်မစာမျက်နှာ",callback_data="home:main")]]))
    elif action == "main":
        await show_menu_page(q,say("welcome",q.from_user.id),private_menu())

async def cleanup_request_group_messages(bot, request_id, recipient_id):
    """Remove public action buttons and obsolete group prompt after private handoff."""
    refs = await db.get_request_group_messages(request_id, recipient_id)
    if not refs:
        return
    gid = refs["recipient_group_id"]
    card_id, prompt_id = refs["group_card_message_id"], refs["group_prompt_message_id"]
    if card_id:
        try:
            await bot.edit_message_reply_markup(chat_id=gid,message_id=card_id,reply_markup=None)
        except TelegramError:
            logging.info("Could not clear request card buttons for request %s",request_id)
    if prompt_id:
        try:
            await bot.delete_message(chat_id=gid,message_id=prompt_id)
        except TelegramError:
            # At minimum remove the button even when deletion is no longer possible.
            try:
                await bot.edit_message_reply_markup(chat_id=gid,message_id=prompt_id,reply_markup=None)
            except TelegramError:
                logging.info("Could not clear private-handoff prompt for request %s",request_id)


async def start(update, context):
    msg = update.effective_message
    if update.effective_chat.type != "private":
        await msg.reply_text(say("welcome", update.effective_user.id))
        return
    args = context.args
    if args and args[0].startswith("reply_"):
        try:
            rid = int(args[0][6:])
        except ValueError:
            await msg.reply_text("💌 ဒီအချစ်စာလေး ဖွင့်လို့မရတော့ဘူးနော်။")
            return ConversationHandler.END
        req = await db.pending_request_for_recipient(rid, update.effective_user.id)
        if not req:
            await msg.reply_text("🌷 ဒီအချစ်စာလေးက အဖြေပြီးသွားတာ ဒါမှမဟုတ် သက်တမ်းကုန်သွားတာ ဖြစ်နိုင်တယ်။")
            return ConversationHandler.END
        sender = await db.get_profile(req["sender_id"], req["sender_group_id"])
        if not sender:
            await msg.reply_text("💌 မိတ်ဆက်ကတ်လေး မရှိတော့ဘူးနော်။")
            return ConversationHandler.END
        keyboard = K([[B("💕 လက်ခံမယ်", callback_data=f"decide:{rid}:accepted")],
                      [B("💔 ငြင်းမယ်", callback_data=f"decide:{rid}:rejected")]])
        await show_profile(context.bot, update.effective_chat.id, sender, keyboard)
        await cleanup_request_group_messages(context.bot,rid,update.effective_user.id)
        return ConversationHandler.END
    if args and args[0].startswith("join_"):
        try:
            gid = int(args[0][5:])
        except ValueError:
            await msg.reply_text("ဒီလင့်ခ်လေး အဆင်မပြေတော့ဘူးနော်။")
            return ConversationHandler.END
        if not (await db.group_settings(gid))["registration"]:
            await msg.reply_text("🌷 ဒီ Group မှာ မိတ်ဆက်ကတ်စာရင်းသွင်းခြင်း ခဏပိတ်ထားတယ်နော်။")
            return ConversationHandler.END
        if not await member(context.bot, gid, update.effective_user.id):
            await msg.reply_text("အဲဒီ Group ထဲမှာ အရင်ဝင်ထားဖို့ လိုတယ်နော် 💗")
            return ConversationHandler.END
        drafts[update.effective_user.id] = {"group_id": gid}
        await msg.reply_text("💌 လူတောင်းပွဲမှာ ပါဝင်ဖို့ အသက် ၁၈ နှစ် ပြည့်ပြီးပြီလား?", reply_markup=K([[B("💗 ပြည့်ပြီးပါပြီ", callback_data="age_confirm:yes")], [B("🌷 မပြည့်သေးပါဘူး", callback_data="age_confirm:no")]]))
        return CONFIRM_AGE
    await msg.reply_text(say("welcome", update.effective_user.id), reply_markup=private_menu())
    return ConversationHandler.END

async def register(update, context):
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("🌷 /register ကို Group ထဲမှာ စတင်ပေးနော်။", reply_markup=private_menu())
        return
    if not (await db.group_settings(update.effective_chat.id))["registration"]:
        await update.message.reply_text("🌷 ဒီ Group မှာ Profile စာရင်းသွင်းခြင်းကို Admin က ခဏပိတ်ထားတယ်နော်။")
        return
    me = await context.bot.get_me()
    url = f"https://t.me/{me.username}?start=join_{update.effective_chat.id}"
    await update.message.reply_text(say("register_invite", update.effective_user.id), reply_markup=K([[B("💗 Profile လေး ဖန်တီးမယ်", url=url)]]))

async def confirm_age(update, context):
    q = update.callback_query
    await q.answer()
    if q.data == "age_confirm:no":
        drafts.pop(q.from_user.id, None)
        await q.edit_message_text("🌷 အသက် ၁၈ နှစ်ပြည့်မှ လူတောင်းပွဲမှာ ပါဝင်လို့ရမယ်နော်။")
        return ConversationHandler.END
    if q.from_user.id not in drafts:
        await q.edit_message_text("💌 Group ထဲက /register နဲ့ ပြန်စလိုက်နော်။")
        return ConversationHandler.END
    drafts[q.from_user.id]["adult_confirmed"] = True
    await q.edit_message_text("💗 ကိုယ့်ကို ဘယ်နာမည်လေးနဲ့ မိတ်ဆက်မလဲ?")
    return NAME

async def name_step(update, context):
    draft = drafts.get(update.effective_user.id)
    if not draft or not draft.get("adult_confirmed"):
        await update.message.reply_text("💌 Group ထဲက /register နဲ့ ပြန်စလိုက်နော်။")
        return ConversationHandler.END
    value = update.message.text.strip()
    if not 1 <= len(value) <= 60:
        await update.message.reply_text("နာမည်လေးကို စာလုံး ၆၀ အောက်နဲ့ ရေးပေးနော်။")
        return NAME
    drafts[update.effective_user.id]["name"] = value
    await update.message.reply_text("📸 ဓာတ်ပုံတစ်ပုံ ဒါမှမဟုတ် စက္ကန့် ၃၀ အောက် Video လေး ပို့ပေးပါ။")
    return MEDIA

async def media_step(update, context):
    msg = update.message
    if msg.photo:
        kind, file_id = "photo", msg.photo[-1].file_id
    elif msg.video and msg.video.duration is not None and msg.video.duration <= 30:
        kind, file_id = "video", msg.video.file_id
    else:
        await msg.reply_text("ဓာတ်ပုံတစ်ပုံ ဒါမှမဟုတ် စက္ကန့် ၃၀ အောက် Video လေး ပို့ပေးနော်။")
        return MEDIA
    if not drafts.get(update.effective_user.id, {}).get("adult_confirmed"):
        await msg.reply_text("💌 /register နဲ့ ပြန်စလိုက်နော်။")
        return ConversationHandler.END
    drafts[update.effective_user.id].update(media_type=kind, file_id=file_id)
    await msg.reply_text("💬 ကိုယ့်အကြောင်း စာတိုလေး ရေးပေးပါ။ မရေးချင်ရင် /skip နှိပ်နိုင်ပါတယ်။")
    return BIO

async def bio_step(update, context):
    d = drafts.get(update.effective_user.id)
    if not d:
        return ConversationHandler.END
    if not await member(context.bot, d["group_id"], update.effective_user.id):
        drafts.pop(update.effective_user.id, None)
        await update.message.reply_text("Group ထဲမှာ မရှိတော့လို့ Profile မသိမ်းထားဘူးနော်။")
        return ConversationHandler.END
    if not d.get("adult_confirmed"):
        drafts.pop(update.effective_user.id, None)
        await update.message.reply_text("💌 /register နဲ့ ပြန်စလိုက်နော်။")
        return ConversationHandler.END
    bio = "" if update.message.text == "/skip" else update.message.text[:300]
    await db.upsert_profile(update.effective_user.id, d["group_id"], d["name"], d["media_type"], d["file_id"], bio)
    drafts.pop(update.effective_user.id, None)
    gid = d["group_id"]
    intro_enabled = (await db.group_settings(gid))["intros"]
    buttons = K([[B("🎀 Group မှာ မိတ်ဆက်မယ်",callback_data=f"intro_yes:{gid}")],
                 [B("🌷 မိတ်ဆက်မပို့တော့ဘူး",callback_data="intro_skip")]]) if intro_enabled else None
    await update.message.reply_text(
        "💖 Profile လေး သိမ်းပြီးပြီ။ Group မှာ မိတ်ဆက်ကတ်တင်မလား? မတင်လည်း /match သုံးလို့ရတယ်နော်။"
        if intro_enabled else say("profile_saved",update.effective_user.id),
        reply_markup=buttons)
    return ConversationHandler.END

async def cancel(update, context):
    drafts.pop(update.effective_user.id, None)
    await update.message.reply_text("နောက်မှ ပြန်လုပ်လို့ရပါတယ်နော် 💗")
    return ConversationHandler.END

def request_card_title(sender, recipient, request_id, *, recipient_id=None, username=None):
    """Short public request caption with a clickable mention of its recipient."""
    from_name = html.escape(sender["display_name"][:40])
    to_name = html.escape(recipient["display_name"][:40])
    if recipient_id is not None:
        # Telegram HTML text mention works for users without public usernames too.
        link = f"tg://user?id={int(recipient_id)}"
        if username and username.lstrip("@").replace("_", "").isalnum():
            username = username.lstrip("@")
            link = "https://t.me/" + username
            to_name += " (@" + html.escape(username) + ")"
        to_name = f'<a href="{html.escape(link, quote=True)}">{to_name}</a>'
    return f"💌 <b>{from_name} က {to_name} ကို လူတောင်းထားပြီ!</b> · #{int(request_id)}\n"


async def request_recipient_username(bot, group_id, user_id):
    """Look up a username if one exists; otherwise HTML mention uses numeric ID."""
    try:
        chat_member = await bot.get_chat_member(group_id, user_id)
        return getattr(chat_member.user, "username", None)
    except TelegramError:
        return None




async def show_profile(bot, chat_id, p, keyboard, *, header="", reply_to_message_id=None):
    kw = {"caption": header + caption(p), "parse_mode": "HTML", "reply_markup": keyboard}
    if reply_to_message_id is not None:
        kw["reply_to_message_id"] = reply_to_message_id
    if p["media_type"] == "video":
        return await bot.send_video(chat_id, p["media_file_id"], **kw)
    return await bot.send_photo(chat_id, p["media_file_id"], **kw)

async def match(update, context):
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("💗 /match ကို Group ထဲမှာ ဖွင့်ပေးနော်။")
        return
    gid, uid = update.effective_chat.id, update.effective_user.id
    if not (await db.group_settings(gid))["matchmaking"]:
        await update.message.reply_text("🌷 ဒီ Group မှာ Matchmaking ကို Admin က ခဏပိတ်ထားတယ်နော်။")
        return
    own = await db.get_profile(uid, gid)
    if not own:
        me = await context.bot.get_me()
        url = f"https://t.me/{me.username}?start=join_{gid}"
        await update.message.reply_text(say("register_invite", uid), reply_markup=K([[B("💗 Profile လေး ဖန်တီးမယ်", url=url)]]))
        return
    existing = await db.active_browse_session(uid, gid)
    if existing:
        await update.message.reply_text(say("match_in_progress",uid))
        return
    results = await db.browse_profiles(uid, gid, public=False, limit=50)
    if not results:
        await update.message.reply_text(say("no_matches", uid))
        return
    p = results[0]
    sent = await show_profile(context.bot, gid, p, match_buttons(uid,gid,p,0,len(results),False))
    keys = [[row["user_id"],row["group_id"]] for row in results]
    await db.save_browse_session(uid,gid,sent.message_id,False,keys)
    await db.mark_profile_viewed(uid,gid,p['user_id'],p['group_id'])
    schedule_browse_timeout(context.bot,uid,gid,sent.message_id)


def match_buttons(uid, gid, p, position, total, public):
    return K([
        [B("⬅️ အရင်တစ်ယောက်", callback_data=f"browse:{uid}:{gid}:-1"),
         B("➡️ နောက်တစ်ယောက်", callback_data=f"browse:{uid}:{gid}:1")],
        [B("🌍 Public" if not public else "🏡 Group Only",
           callback_data=f"browse_mode:{uid}:{gid}")],
        [B("💌 တောင်းမယ်", callback_data=f"ask:{uid}:{gid}:{p['user_id']}:{p['group_id']}")],
    ])

async def edit_browse_card(q, uid, gid, p, pos, count, public):
    kwargs = {"caption": caption(p), "parse_mode": "HTML"}
    if p["media_type"] == "video":
        media = InputMediaVideo(p["media_file_id"], **kwargs)
    else:
        media = InputMediaPhoto(p["media_file_id"], **kwargs)
    await q.edit_message_media(media=media, reply_markup=match_buttons(uid,gid,p,pos,count,public))

async def browse_callback(update, context):
    q = update.callback_query
    try:
        _, uid_text, gid_text, delta_text = q.data.split(":")
        uid, gid, delta = int(uid_text), int(gid_text), int(delta_text)
    except (ValueError, AttributeError):
        await q.answer("ကတ်လေး အဆင်မပြေတော့ဘူးနော်။", show_alert=True)
        return
    if q.from_user.id != uid or q.message.chat.id != gid:
        await q.answer("ကိုယ့်မိတ်ဆက်ကတ်လေးမှာပဲ လှည့်ကြည့်နိုင်တယ်နော်။", show_alert=True)
        return
    session = await db.advance_browse_session(uid,gid,q.message.message_id,delta)
    if not session:
        await q.answer("🌷 ကတ်လေး သက်တမ်းကုန်သွားပြီ။ /match နဲ့ ပြန်စကြမယ်နော်။", show_alert=True)
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except TelegramError:
            pass
        return
    keys = session["profile_keys"]
    if isinstance(keys, str):
        keys = json.loads(keys)
    if not keys:
        await q.answer("လှည့်ကြည့်ဖို့ Profile မရှိတော့ဘူးနော်။", show_alert=True)
        return
    key = keys[session["position"]]
    p = await db.get_profile(key[0],key[1])
    if not p:
        await q.answer("ဒီ Profile လေး မရှိတော့ဘူးနော်။", show_alert=True)
        return
    if delta > 0 and session["position"] == len(keys)-1:
        await q.answer("💗 နောက်ဆုံးကတ်လေးအထိ ရောက်နေပြီနော်။")
    elif delta < 0 and session["position"] == 0:
        await q.answer("🌷 ပထမဆုံးကတ်လေးအထိ ရောက်နေပြီနော်။")
    else:
        await q.answer()
    schedule_browse_timeout(context.bot,uid,gid,q.message.message_id)
    try:
        await edit_browse_card(q,uid,gid,p,session["position"],len(keys),session["public_mode"])
        await db.mark_profile_viewed(uid,gid,p["user_id"],p["group_id"])
    except TelegramError:
        logging.exception("Failed to edit browse card")

async def browse_mode_callback(update, context):
    q = update.callback_query
    try:
        _, uid_text, gid_text = q.data.split(":")
        uid, gid = int(uid_text), int(gid_text)
    except (ValueError,AttributeError):
        await q.answer("ကတ်လေး အဆင်မပြေတော့ဘူးနော်။",show_alert=True)
        return
    if q.from_user.id != uid or q.message.chat.id != gid:
        await q.answer("ကိုယ့်ကတ်လေးမှာပဲ ပြောင်းနိုင်တယ်နော်။",show_alert=True)
        return
    session = await db.active_browse_session(uid,gid)
    if not session or session["message_id"] != q.message.message_id:
        await q.answer("ကတ်လေး သက်တမ်းကုန်သွားပြီနော်။",show_alert=True)
        return
    settings = await db.group_settings(gid)
    public = not session["public_mode"]
    if public and not settings["public_browse"]:
        await q.answer("🌷 ဒီ Group မှာ Public Browse ကို Admin က ပိတ်ထားတယ်နော်။",show_alert=True)
        return
    results = await db.browse_profiles(uid,gid,public=public,limit=50)
    if not results:
        await q.answer("💌 ဒီ Mode မှာ Profile အသစ် မရှိသေးဘူးနော်။",show_alert=True)
        return
    keys = [[r["user_id"],r["group_id"]] for r in results]
    await db.save_browse_session(uid,gid,q.message.message_id,public,keys)
    schedule_browse_timeout(context.bot,uid,gid,q.message.message_id)
    await q.answer("🌍 Public Browse" if public else "🏡 Group Only")
    try:
        await edit_browse_card(q,uid,gid,results[0],0,len(results),public)
        await db.mark_profile_viewed(uid,gid,results[0]["user_id"],results[0]["group_id"])
    except TelegramError:
        logging.exception("Failed to switch browse mode")

async def ask_callback(update, context):
    q = update.callback_query
    try:
        _, invoker, source_group, target_user, target_group = q.data.split(":")
        invoker, source_group, target_user, target_group = map(int, (invoker,source_group,target_user,target_group))
    except (ValueError, AttributeError):
        await q.answer("ခလုတ်လေး သက်တမ်းကုန်သွားပြီ။", show_alert=True)
        return
    if q.from_user.id != invoker or q.message.chat.id != source_group:
        await q.answer("ဒီခလုတ်လေးက Profile ကြည့်နေသူအတွက်ပဲနော် 💗", show_alert=True)
        return
    session = await db.active_browse_session(invoker,source_group)
    if not session or session["message_id"] != q.message.message_id:
        await q.answer("🌷 ဒီမိတ်ဆက်ကတ်လေး သက်တမ်းကုန်ပြီ။ /match နဲ့ ပြန်စကြမယ်နော်။", show_alert=True)
        return
    keys = session["profile_keys"]
    if isinstance(keys, str):
        keys = json.loads(keys)
    if (not keys or [target_user,target_group] != keys[session["position"]]):
        await q.answer("🌷 အခုကြည့်နေတဲ့ Profile ကတ်လေးမှာပဲ တောင်းပေးနော်။", show_alert=True)
        return
    if not await member(context.bot, source_group, invoker) or not await member(context.bot, target_group, target_user):
        await q.answer("Group အဖွဲ့ဝင်အခြေအနေ ပြောင်းသွားပြီနော်။", show_alert=True)
        return
    source = await db.get_profile(invoker, source_group)
    target = await db.get_profile(target_user, target_group)
    if not source or not target:
        await q.answer("Profile လေး မရှိတော့ဘူးနော်။", show_alert=True)
        return
    if not (await db.group_settings(source_group))["requests"]:
        await q.answer("🌷 ဒီ Group မှာ Request ပို့ခြင်းကို ခဏပိတ်ထားတယ်နော်။", show_alert=True)
        return
    await q.answer()
    await q.message.reply_text(f"💌 <b>{html.escape(source['display_name'])}</b> က <b>{html.escape(target['display_name'])}</b> ဆီ ဖိတ်ခေါ်စာ ပို့မလား?",
        parse_mode="HTML", reply_to_message_id=q.message.message_id,
        reply_markup=K([[B("💕 သေချာပို့မယ်",callback_data=f"ask_confirm:{invoker}:{source_group}:{target_user}:{target_group}")],
                        [B("🌷 မပို့တော့ဘူး",callback_data=f"ask_cancel:{invoker}:{source_group}:{target_user}:{target_group}")]]))
    return

async def ask_confirm_callback(update, context):
    q = update.callback_query
    try:
        _, invoker, source_group, target_user, target_group = q.data.split(":")
        invoker, source_group, target_user, target_group = map(int,(invoker,source_group,target_user,target_group))
    except (AttributeError,ValueError):
        await q.answer("ခလုတ်လေး အဆင်မပြေတော့ဘူး။",show_alert=True)
        return
    if q.from_user.id != invoker or q.message.chat.id != source_group:
        await q.answer("ဖိတ်ခေါ်စာပိုင်ရှင်ပဲ အတည်ပြုနိုင်တယ်နော်။",show_alert=True)
        return
    if q.data.startswith("ask_cancel:"):
        await q.answer()
        await q.edit_message_text("🌷 ဖိတ်ခေါ်စာလေး မပို့တော့ဘူးနော်။")
        return
    session = await db.active_browse_session(invoker,source_group)
    if not session:
        await q.answer("မိတ်ဆက်ကတ်လေး သက်တမ်းကုန်သွားပြီနော်။",show_alert=True)
        return
    keys = session["profile_keys"]
    if isinstance(keys,str):
        keys = json.loads(keys)
    if (not keys or [target_user,target_group] != keys[session["position"]]
            or not (await db.group_settings(source_group))["requests"]):
        await q.answer("မိတ်ဆက်ကတ်လေး ပြောင်းသွားပြီနော်။",show_alert=True)
        return
    if not await member(context.bot,source_group,invoker) or not await member(context.bot,target_group,target_user):
        await q.answer("Group အဖွဲ့ဝင်အခြေအနေ ပြောင်းသွားပြီနော်။",show_alert=True)
        return
    source = await db.get_profile(invoker,source_group)
    target = await db.get_profile(target_user,target_group)
    if not source or not target:
        await q.answer("Profile လေး မရှိတော့ဘူးနော်။",show_alert=True)
        return
    touched = await db.touch_browse_session(invoker,source_group,session["message_id"])
    if not touched:
        await q.answer("ဒီမိတ်ဆက်ကတ်လေး သက်တမ်းကုန်သွားပြီနော်။",show_alert=True)
        return
    schedule_browse_timeout(context.bot,invoker,source_group,session["message_id"])
    result = await db.send_request(invoker, source_group, target_user, target_group)
    if not result:
        await q.answer("အချစ်စာလေး ပို့ထားပြီးသား ဖြစ်နိုင်ပါတယ် 💌", show_alert=True)
        return
    await q.answer("အချစ်စာလေး ပို့လိုက်ပြီ 💌")
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass
    try:
        card = await show_profile(context.bot, target_group, source,
            K([[B("💌 အဖြေပေးမယ်", callback_data=f"reply:{result['id']}:{target_user}")]]),
            header=request_card_title(
                source,target,result["id"],recipient_id=target_user,
                username=await request_recipient_username(context.bot,target_group,target_user)),
            reply_to_message_id=session["message_id"] if source_group == target_group else None)
        await db.remember_request_group_message(result["id"],target_user,"card",card.message_id)
    except TelegramError:
        logging.exception("Request group delivery failed; request persisted")

async def reply_callback(update, context):
    q = update.callback_query
    try:
        _, request_id, target = q.data.split(":")
        request_id, target = int(request_id), int(target)
    except (ValueError, AttributeError):
        await q.answer("ခလုတ်လေး အဆင်မပြေတော့ဘူး။", show_alert=True)
        return
    if q.from_user.id != target:
        await q.answer("ဒီအချစ်စာလေးက ပိုင်ရှင်အတွက်ပဲနော် 💗", show_alert=True)
        return
    req = await db.pending_request_for_recipient(request_id,target)
    if not req:
        await q.answer("ဒီဖိတ်ခေါ်စာလေး အဖြေပေးပြီးသား ဒါမှမဟုတ် သက်တမ်းကုန်သွားပြီနော်။",show_alert=True)
        await cleanup_request_group_messages(context.bot,request_id,target)
        return
    refs = await db.get_request_group_messages(request_id,target)
    if refs and refs["group_prompt_message_id"]:
        await q.answer("Private ကိုသွားဖို့ ခလုတ်လေး ပေးပြီးသားနော်။",show_alert=True)
        return
    me = await context.bot.get_me()
    await q.answer()
    prompt = await q.message.reply_text("💌 ဒီ Request ကို Private Chat မှာ အဖြေပေးနိုင်တယ်နော်။",
        reply_to_message_id=q.message.message_id,
        reply_markup=K([[B("💗 Private မှာ အဖြေပေးမယ်", url=f"https://t.me/{me.username}?start=reply_{request_id}")]]))
    await db.remember_request_group_message(request_id,target,"prompt",prompt.message_id)

async def decide_callback(update, context):
    q = update.callback_query
    try:
        _, request_id, action = q.data.split(":")
        request_id = int(request_id)
    except (AttributeError, ValueError):
        await q.answer("ခလုတ်လေး အဆင်မပြေတော့ဘူး။", show_alert=True)
        return
    if action not in ("accepted", "rejected") or q.message.chat.type != "private":
        await q.answer("ဒီနေရာကနေ အဖြေပေးလို့မရဘူးနော်။", show_alert=True)
        return
    result = await db.resolve_request(request_id, q.from_user.id, action)
    if not result:
        await q.answer("ဒီအချစ်စာလေးကို အဖြေပေးပြီးသား ဖြစ်နိုင်ပါတယ်။", show_alert=True)
        return
    await q.answer("အဖြေလေး သိမ်းထားပြီ 💗")
    await cleanup_request_group_messages(context.bot,request_id,q.from_user.id)
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        logging.exception("Could not disable answered request buttons")
    sender_id, recipient_id = result["sender_id"], result["recipient_id"]
    if action == "rejected":
        await q.message.reply_text("🌷 ဒီဖိတ်ခေါ်စာကို ငြင်းလိုက်ပြီနော်။ အကြောင်းပြချက်လေးကို မျှဝေချင်မှပဲ ပို့ပေးနိုင်တယ်။",
            reply_markup=K([[B("💬 စကားလေး ထပ်ပြောမယ်",callback_data=f"reason_start:{request_id}")],
                            [B("🌷 ဘာမှမပြောတော့ဘူး",callback_data="reason_skip")]]))
        try:
            await context.bot.send_message(sender_id, say("request_rejected",sender_id))
        except TelegramError:
            logging.info("Sender private chat unavailable for rejection notice")
        return
    a = f'<a href="tg://user?id={sender_id}">မိတ်ဆက်ဖိတ်ခေါ်သူ</a>'
    b = f'<a href="tg://user?id={recipient_id}">လက်ခံသူ</a>'
    announcement = f"💕 <b>{html.escape(say('request_accepted',recipient_id))}</b>\n{a} နဲ့ {b} တို့ မိတ်ဆက်ခွင့်ရသွားပြီနော် 💌"
    for gid in {result["sender_group_id"], result["recipient_group_id"]}:
        try:
            await context.bot.send_message(gid, announcement, parse_mode="HTML")
        except TelegramError:
            logging.info("Group announcement could not be delivered")
    for user_id, other_id in ((sender_id, recipient_id), (recipient_id, sender_id)):
        try:
            await context.bot.send_message(
                user_id,
                f'💗 နှစ်ဖက်လုံး သဘောတူပြီးပြီနော်။ <a href="tg://user?id={other_id}">ဒီမှာ မိတ်ဆက်စကား စပြောနိုင်ပြီ 💌</a>',
                parse_mode="HTML")
        except TelegramError:
            logging.info("Private contact notice could not be delivered")


async def reason_start(update, context):
    q = update.callback_query
    if q.message.chat.type != "private":
        await q.answer("Private မှာပဲ ပြောပေးနော်။",show_alert=True)
        return ConversationHandler.END
    if q.data == "reason_skip":
        await q.answer()
        await q.edit_message_text("🌷 အကြောင်းပြချက် မမျှဝေတော့ဘူးနော်။")
        return ConversationHandler.END
    try:
        rid = int(q.data.split(":",1)[1])
    except (ValueError,AttributeError):
        await q.answer("ခလုတ်လေး အဆင်မပြေတော့ဘူး။",show_alert=True)
        return ConversationHandler.END
    req = await db.rejected_request_owned(rid,q.from_user.id)
    if not req or req["rejection_reason"] is not None:
        await q.answer("ဒီစာအတွက် ထပ်ပြောလို့မရတော့ဘူးနော်။",show_alert=True)
        return ConversationHandler.END
    context.user_data["reason_draft"] = {"rid":rid}
    await q.answer()
    await q.message.reply_text("💬 မျှဝေချင်တဲ့ စကားလေးကို စာလုံး ၂၀၀ အောက်နဲ့ ရေးပေးနော်။ /cancel နဲ့ ရပ်လို့ရတယ်။")
    return REJECTION_TEXT

async def reason_text(update, context):
    draft = context.user_data.get("reason_draft")
    if not draft:
        return ConversationHandler.END
    message = update.message.text.strip()
    if not 1 <= len(message) <= 200:
        await update.message.reply_text("🌷 စာလုံး ၁ လုံးကနေ ၂၀၀ အထိပဲ ရေးပေးနော်။")
        return REJECTION_TEXT
    draft["text"] = message
    await update.message.reply_text(
        "💌 ဒီစကားလေးကို တစ်ဖက်ကို တကယ်မျှဝေမလား?\n\n"+message,
        reply_markup=K([[B("💌 သဘောတူတယ်၊ မျှဝေမယ်",callback_data="reason_send")],
                        [B("🌷 မပို့တော့ဘူး",callback_data="reason_cancel")]]))
    return ConversationHandler.END

async def reason_finish(update, context):
    q = update.callback_query
    if q.message.chat.type != "private":
        await q.answer("Private မှာပဲ လုပ်ပေးနော်။",show_alert=True)
        return
    draft = context.user_data.pop("reason_draft",None)
    if q.data == "reason_cancel":
        await q.answer()
        await q.edit_message_text("🌷 စကားလေး မမျှဝေတော့ဘူးနော်။")
        return
    if not draft or not draft.get("text"):
        await q.answer("အတည်ပြုစရာ စကားလေး မရှိတော့ဘူးနော်။",show_alert=True)
        return
    req = await db.save_rejection_reason(draft["rid"],q.from_user.id,draft["text"])
    if not req:
        await q.answer("ဒီစာလေးကို မျှဝေလို့မရတော့ဘူးနော်။",show_alert=True)
        return
    await q.answer("စကားလေး မျှဝေပြီးပြီ")
    await q.edit_message_text("💌 ကိုယ်သဘောတူတဲ့ စကားလေးကို မျှဝေပြီးပြီနော်။")
    try:
        await context.bot.send_message(req["sender_id"],
            "🌷 ဖိတ်ခေါ်စာအတွက် တစ်ဖက်က မျှဝေဖို့ သဘောတူထားတဲ့ စကားလေးပါ။\n\n"+draft["text"])
    except TelegramError:
        logging.info("Could not deliver optional rejection note")

async def reason_cancel(update, context):
    context.user_data.pop("reason_draft",None)
    await update.message.reply_text("🌷 စကားလေး မမျှဝေတော့ဘူးနော်။")
    return ConversationHandler.END

async def inbox(update, context):
    """Private, unified newest-first incoming requests; no polling."""
    if update.effective_chat.type != "private":
        await update.message.reply_text("💌 အချစ်စာဝင်ပုံးကို Private Chat မှာ ဖွင့်ကြည့်ပေးနော်။")
        return
    items = await db.incoming_requests(update.effective_user.id)
    if not items:
        await update.message.reply_text(say("inbox_empty",update.effective_user.id))
        return
    buttons = []
    for row in items[:30]:
        sender = await db.get_profile(row["sender_id"], row["sender_group_id"])
        if sender:
            title = sender["display_name"][:25]
            buttons.append([B(f"💌 {title}", callback_data=f"inbox_open:{row['id']}")])
    if not buttons:
        await update.message.reply_text("🌷 ဖွင့်ကြည့်လို့ရတဲ့ အချစ်စာလေး မရှိတော့ဘူးနော်။")
        return
    await update.message.reply_text(
        f"💌 <b>ဝင်လာတဲ့ အချစ်စာလေးများ</b>\nအဖြေစောင့်နေတဲ့ စာ {len(items)} စောင် ရှိတယ်နော်။",
        parse_mode="HTML", reply_markup=K(buttons))

async def inbox_open(update, context):
    q = update.callback_query
    try:
        request_id = int(q.data.split(":", 1)[1])
    except (ValueError, AttributeError):
        await q.answer("စာလေး ဖွင့်လို့မရတော့ဘူးနော်။", show_alert=True)
        return
    if q.message.chat.type != "private":
        await q.answer("Private Chat မှာပဲ ဖွင့်ပေးနော်။", show_alert=True)
        return
    req = await db.pending_request_for_recipient(request_id, q.from_user.id)
    if not req:
        await q.answer("ဒီစာလေး သက်တမ်းကုန်သွားပြီ ဒါမှမဟုတ် အဖြေပြီးပြီနော်။", show_alert=True)
        return
    sender = await db.get_profile(req["sender_id"], req["sender_group_id"])
    if not sender:
        await q.answer("Profile လေး မရှိတော့ဘူးနော်။", show_alert=True)
        return
    await q.answer()
    try:
        await q.message.delete()
    except TelegramError:
        logging.info("Inbox picker could not be deleted")
    await show_profile(context.bot, q.from_user.id, sender,
        K([[B("💕 လက်ခံမယ်", callback_data=f"decide:{request_id}:accepted")],
           [B("💔 ငြင်းမယ်", callback_data=f"decide:{request_id}:rejected")]]))

async def outgoing(update, context):
    if update.effective_chat.type != "private":
        await update.message.reply_text("💌 ပို့ထားတဲ့ စာလေးတွေကို Private Chat မှာ ကြည့်ပေးနော်။")
        return
    items = await db.outgoing_requests(update.effective_user.id)
    if not items:
        await update.message.reply_text(say("outgoing_empty",update.effective_user.id))
        return
    buttons = []
    for row in items[:30]:
        target = await db.get_profile(row["recipient_id"], row["recipient_group_id"])
        if target:
            buttons.append([B(f"💌 {target['display_name'][:25]} · ပြန်ရုပ်သိမ်းမယ်",
                              callback_data=f"withdraw_ask:{row['id']}")])
    await update.message.reply_text(
        f"💌 <b>ပို့ထားတဲ့ ဖိတ်ခေါ်စာများ</b>\nအဖြေစောင့်နေတဲ့ စာ {len(items)} စောင် ရှိတယ်နော်။",
        parse_mode="HTML", reply_markup=K(buttons) if buttons else None)

async def withdraw_ask(update, context):
    q = update.callback_query
    if q.message.chat.type != "private":
        await q.answer("Private Chat မှာပဲ လုပ်ပေးနော်။", show_alert=True)
        return
    try:
        rid = int(q.data.split(":", 1)[1])
    except (ValueError, AttributeError):
        await q.answer("ဒီခလုတ်လေး အဆင်မပြေတော့ဘူးနော်။", show_alert=True)
        return
    owned = await db.outgoing_requests(q.from_user.id)
    if not any(row["id"] == rid for row in owned):
        await q.answer("ဒီစာလေး အဖြေပြီးသွားတာ ဒါမှမဟုတ် သက်တမ်းကုန်သွားပြီ။", show_alert=True)
        return
    await q.answer()
    await show_menu_page(q, "💌 ဒီဖိတ်ခေါ်စာလေးကို တကယ် ပြန်ရုပ်သိမ်းမလား?",
        K([[B("💔 ပြန်ရုပ်သိမ်းမယ်", callback_data=f"withdraw_do:{rid}")],
                        [B("🌷 မရုပ်သိမ်းတော့ဘူး", callback_data="withdraw_cancel")]]))

async def withdraw_do(update, context):
    q = update.callback_query
    if q.message.chat.type != "private":
        await q.answer("Private Chat မှာပဲ လုပ်ပေးနော်။", show_alert=True)
        return
    if q.data == "withdraw_cancel":
        await q.answer()
        await q.edit_message_text("💗 ဒီစာလေးကို ဆက်စောင့်ကြည့်လို့ရတယ်နော်။")
        return
    try:
        rid = int(q.data.split(":", 1)[1])
    except (ValueError, AttributeError):
        await q.answer("ခလုတ်လေး မမှန်တော့ဘူးနော်။", show_alert=True)
        return
    result = await db.withdraw_request(rid, q.from_user.id)
    if not result:
        await q.answer("ဒီစာလေးကို ပြန်ရုပ်သိမ်းလို့ မရတော့ဘူးနော်။", show_alert=True)
        return
    await q.answer("ပြန်ရုပ်သိမ်းပြီးပြီ 💗")
    await q.edit_message_text(say("request_withdrawn",q.from_user.id))


async def profile(update, context):
    """List own profiles in private; public selection is opt-in."""
    if update.effective_chat.type != "private":
        await update.message.reply_text("💗 Profile လေးတွေကို Private Chat မှာပဲ စီမံကြမယ်နော်။")
        return
    rows = await db.user_profiles(update.effective_user.id)
    if not rows:
        await update.message.reply_text("🌷 Profile လေး မရှိသေးဘူးနော်။ Group ထဲက /register နဲ့ စကြမယ်။", reply_markup=private_menu())
        return
    buttons = []
    for row in rows:
        label = ("🌍 " if row["is_public"] else "💗 ") + row["display_name"][:25]
        buttons.append([B(label, callback_data=f"profile_view:{row['group_id']}")])
    await update.message.reply_text(
        f"💗 <b>ကိုယ့် Profile လေးများ</b>\nProfile {len(rows)} ခု ရှိတယ်နော်။ 🌍 ဆိုတာ Public ဖွင့်ထားတဲ့ Profile ပါ။",
        parse_mode="HTML", reply_markup=K(buttons))

def profile_actions(group_id, public):
    toggle = B("🌷 Public ပိတ်မယ်" if public else "🌍 Public ဖွင့်မယ်",
               callback_data=f"profile_public:{group_id}:{0 if public else 1}")
    return K([[toggle],
              [B("✏️ နာမည်ပြင်မယ်", callback_data=f"profile_edit:{group_id}:display_name"),
               B("💬 Bio ပြင်မယ်", callback_data=f"profile_edit:{group_id}:bio")],
              [B("📸 ပုံ/Video ပြင်မယ်", callback_data=f"profile_edit:{group_id}:media")],
              [B("🗑 Profile ဖျက်မယ်", callback_data=f"profile_delete_ask:{group_id}")],
              [B("💗 ပင်မစာမျက်နှာ", callback_data="home:main")]])

async def profile_view(update, context):
    q = update.callback_query
    if q.message.chat.type != "private":
        await q.answer("Private Chat မှာပဲ ဖွင့်ပေးနော်။", show_alert=True)
        return
    try:
        group_id = int(q.data.split(":", 1)[1])
    except (ValueError, AttributeError):
        await q.answer("ဒီခလုတ်လေး အဆင်မပြေတော့ဘူး။", show_alert=True)
        return
    p = await db.get_profile(q.from_user.id, group_id)
    if not p:
        await q.answer("Profile လေး မရှိတော့ဘူးနော်။", show_alert=True)
        return
    await q.answer()
    actions = profile_actions(group_id, bool(p["is_public"]))
    # Telegram cannot turn a text message into a photo/video by editing it.
    # Delete the old inline list before sending a media profile card.
    try:
        await q.message.delete()
    except TelegramError:
        logging.warning("Cannot remove prior profile picker; retaining it")
        return
    await show_profile(context.bot, q.from_user.id, p, actions)

async def profile_public(update, context):
    q = update.callback_query
    if q.message.chat.type != "private":
        await q.answer("Private Chat မှာပဲ ပြောင်းနိုင်တယ်နော်။", show_alert=True)
        return
    try:
        _, group_str, state_str = q.data.split(":")
        gid, state = int(group_str), int(state_str)
    except (AttributeError, ValueError):
        await q.answer("ဒီခလုတ်လေး အဆင်မပြေတော့ဘူး။", show_alert=True)
        return
    p = await db.get_profile(q.from_user.id, gid)
    if not p or state not in (0, 1):
        await q.answer("Profile လေး မရှိတော့ဘူးနော်။", show_alert=True)
        return
    if state:
        if not await member(context.bot, gid, q.from_user.id):
            await q.answer("အဲဒီ Group ထဲမှာ မရှိတော့လို့ Public မဖွင့်နိုင်ဘူးနော်။", show_alert=True)
            return
        result = await db.set_public_profile(q.from_user.id, gid)
        if not result:
            await q.answer("Profile လေး မရှိတော့ဘူးနော်။", show_alert=True)
            return
    else:
        await db.set_private_profile(q.from_user.id, gid)
    await q.answer("💗 Profile အပြင်အဆင် သိမ်းပြီးပြီ။")
    await q.edit_message_reply_markup(reply_markup=profile_actions(gid,bool(state)))



async def profile_edit_begin(update, context):
    q = update.callback_query
    if q.message.chat.type != "private":
        await q.answer("Private Chat မှာပဲ ပြင်ကြမယ်နော်။",show_alert=True)
        return ConversationHandler.END
    try:
        _, gid_str, field = q.data.split(":")
        gid = int(gid_str)
    except (ValueError, AttributeError):
        await q.answer("ခလုတ်လေး အဆင်မပြေတော့ဘူး။",show_alert=True)
        return ConversationHandler.END
    if field not in ("display_name","bio","media") or not await db.get_profile(q.from_user.id,gid):
        await q.answer("Profile လေး မရှိတော့ဘူးနော်။",show_alert=True)
        return ConversationHandler.END
    context.user_data["profile_edit"] = {"group_id":gid,"field":field}
    await q.answer()
    if field == "media":
        await q.message.reply_text("📸 ပုံအသစ် ဒါမှမဟုတ် စက္ကန့် ၃၀ အောက် Video လေး ပို့ပေးနော်။ /cancel နဲ့ ရပ်နိုင်တယ်။")
        return EDIT_MEDIA
    await q.message.reply_text(
        "💗 နာမည်အသစ်လေး ရေးပေးနော်။" if field == "display_name"
        else "💬 Bio အသစ်လေး ရေးပေးနော်။ မထည့်ချင်ရင် /skip လို့ပို့ပါ။")
    return EDIT_TEXT

async def profile_edit_text(update, context):
    edit = context.user_data.get("profile_edit")
    if not edit or edit["field"] not in ("display_name","bio"):
        return ConversationHandler.END
    value = update.message.text.strip()
    field = edit["field"]
    if field == "display_name" and not (1 <= len(value) <= 60):
        await update.message.reply_text("နာမည်လေးကို စာလုံး ၁ လုံးကနေ ၆၀ လုံးအထိ ရေးပေးနော်။")
        return EDIT_TEXT
    if field == "bio":
        value = "" if value == "/skip" else value
        if len(value) > 300:
            await update.message.reply_text("Bio လေးကို စာလုံး ၃၀၀ အောက်ပဲ ရေးပေးနော်။")
            return EDIT_TEXT
    result = await db.update_profile_text(update.effective_user.id, edit["group_id"],field,value)
    context.user_data.pop("profile_edit",None)
    await update.message.reply_text(say("profile_updated",update.effective_user.id) if result else "🌷 Profile လေး မရှိတော့ဘူးနော်။")
    return ConversationHandler.END

async def profile_edit_media(update, context):
    edit = context.user_data.get("profile_edit")
    if not edit or edit["field"] != "media":
        return ConversationHandler.END
    message = update.message
    if message.photo:
        kind, fid = "photo", message.photo[-1].file_id
    elif message.video and message.video.duration is not None and message.video.duration <= 30:
        kind, fid = "video", message.video.file_id
    else:
        await message.reply_text("🌷 ဓာတ်ပုံ ဒါမှမဟုတ် စက္ကန့် ၃၀ အောက် Video လေးပဲ ပို့ပေးနော်။")
        return EDIT_MEDIA
    result = await db.update_profile_media(update.effective_user.id,edit["group_id"],kind,fid)
    context.user_data.pop("profile_edit",None)
    await message.reply_text(say("profile_updated",update.effective_user.id) if result else "🌷 Profile လေး မရှိတော့ဘူးနော်။")
    return ConversationHandler.END

async def profile_edit_cancel(update, context):
    context.user_data.pop("profile_edit",None)
    await update.message.reply_text("🌷 မပြင်တော့ဘူးဆိုလည်း ရပါတယ်နော်။")
    return ConversationHandler.END

async def profile_delete_ask(update, context):
    q = update.callback_query
    if q.message.chat.type != "private":
        await q.answer("Private Chat မှာပဲ လုပ်ပေးနော်။",show_alert=True)
        return
    try:
        gid = int(q.data.split(":",1)[1])
    except (AttributeError,ValueError):
        await q.answer("ခလုတ်လေး အဆင်မပြေတော့ဘူးနော်။",show_alert=True)
        return
    if not await db.get_profile(q.from_user.id,gid):
        await q.answer("Profile လေး မရှိတော့ဘူးနော်။",show_alert=True)
        return
    await q.answer()
    await q.edit_message_caption(caption="🗑 ဒီ Group အတွက် Profile လေးကို တကယ်ဖျက်မလား? ဖျက်ပြီးရင် ပြန်ယူလို့မရဘူးနော်။",
        reply_markup=K([[B("🗑 သေချာဖျက်မယ်",callback_data=f"profile_delete_do:{gid}")],
                        [B("🌷 မဖျက်တော့ဘူး",callback_data="profile_delete_cancel")]]))

async def profile_delete_do(update, context):
    q = update.callback_query
    if q.message.chat.type != "private":
        await q.answer("Private Chat မှာပဲ လုပ်ပေးနော်။",show_alert=True)
        return
    if q.data == "profile_delete_cancel":
        await q.answer()
        await q.edit_message_caption(caption="💗 Profile လေးကို ဆက်သိမ်းထားမယ်နော်။",reply_markup=None)
        return
    try:
        gid = int(q.data.split(":",1)[1])
    except (AttributeError,ValueError):
        await q.answer("ခလုတ်လေး အဆင်မပြေတော့ဘူးနော်။",show_alert=True)
        return
    result = await db.delete_profile(q.from_user.id,gid)
    if result is None:
        await q.answer("Profile လေး မရှိတော့ဘူးနော်။",show_alert=True)
        return
    await q.answer("Profile ဖျက်ပြီးပြီ")
    await q.edit_message_caption(caption=say("profile_deleted",q.from_user.id),reply_markup=None)
    for card in result.get("old_cards", []):
        if card["message_id"] is None:
            continue
        key = (card["viewer_id"], card["group_id"])
        timer = _browse_timer_tasks.pop(key,None)
        if timer and not timer.done():
            timer.cancel()
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=card["group_id"],message_id=card["message_id"],reply_markup=None)
        except TelegramError:
            logging.info("Old browse card not editable after deletion")
    affected = {r["sender_id"] for r in result["affected"] if r["sender_id"] != q.from_user.id}
    for uid in affected:
        try:
            await context.bot.send_message(uid,"💌 ပို့ထားတဲ့ မိတ်ဆက်ဖိတ်ခေါ်ချက်တစ်ခုဟာ Profile ဖျက်လိုက်လို့ မရနိုင်တော့ဘူးနော်။")
        except TelegramError:
            logging.info("Unable to notify affected requester")


async def intro_callback(update, context):
    """Only the profile owner may voluntarily publish an introduction."""
    q = update.callback_query
    if q.message.chat.type != "private":
        await q.answer("Private မှာပဲ ရွေးပေးနော်။",show_alert=True)
        return
    if q.data == "intro_skip":
        await q.answer()
        await q.edit_message_text("🌷 မိတ်ဆက်ကတ် မတင်တော့ဘူးနော်။ Group မှာ /match နဲ့ လှည့်ကြည့်လို့ရပြီ။")
        return
    try:
        gid = int(q.data.split(":",1)[1])
    except (ValueError,AttributeError):
        await q.answer("ခလုတ်လေး အဆင်မပြေတော့ဘူး။",show_alert=True)
        return
    p = await db.get_profile(q.from_user.id,gid)
    if not p or not await member(context.bot,gid,q.from_user.id):
        await q.answer("Group ထဲမှာ ကိုယ့် Profile မရှိတော့ဘူးနော်။",show_alert=True)
        return
    if not (await db.group_settings(gid))["intros"]:
        await q.answer("မိတ်ဆက်ကတ်တင်တာကို Group Admin က ပိတ်ထားတယ်နော်။",show_alert=True)
        return
    await q.answer()
    try:
        await show_profile(context.bot,gid,p,K([[B("💌 မိတ်ဆက်ခွင့် တောင်းမယ်",
            callback_data=f"intro_view:{q.from_user.id}:{gid}")]]))
    except TelegramError:
        logging.exception("Failed to publish voluntary introduction")
        await q.message.reply_text("🌷 Group ထဲကို မိတ်ဆက်ကတ် မပို့နိုင်သေးဘူးနော်။")
        return
    await q.edit_message_text(say("intro_published",q.from_user.id))

async def intro_view(update, context):
    """A visitor can request an introduction from the owner's group card."""
    q = update.callback_query
    try:
        _, target_text, gid_text = q.data.split(":")
        target_id, gid = int(target_text), int(gid_text)
    except (ValueError, AttributeError):
        await q.answer("မိတ်ဆက်ကတ်လေး အဆင်မပြေတော့ဘူး။",show_alert=True)
        return
    sender_id = q.from_user.id
    if q.message.chat.id != gid or sender_id == target_id:
        await q.answer("ဒီမိတ်ဆက်ကတ်လေးမှာ တောင်းလို့မရဘူးနော်။",show_alert=True)
        return
    settings = await db.group_settings(gid)
    if not settings["requests"] or not settings["intros"]:
        await q.answer("ဒီ Group မှာ မိတ်ဆက်ခွင့် တောင်းတာကို ခဏပိတ်ထားတယ်နော်။",show_alert=True)
        return
    if not await member(context.bot,gid,sender_id) or not await member(context.bot,gid,target_id):
        await q.answer("Group ထဲမှာ အဖွဲ့ဝင်ဖြစ်ဖို့ လိုတယ်နော်။",show_alert=True)
        return
    source = await db.get_profile(sender_id,gid)
    target = await db.get_profile(target_id,gid)
    if not source:
        me = await context.bot.get_me()
        url = f"https://t.me/{me.username}?start=join_{gid}"
        await q.answer("Profile လေး အရင်ဖန်တီးကြမယ်နော်။")
        await q.message.reply_text(say("register_invite",sender_id),
            reply_markup=K([[B("💗 Profile လေး ဖန်တီးမယ်",url=url)]]))
        return
    if not target:
        await q.answer("မိတ်ဆက်ကတ်ပိုင်ရှင်ရဲ့ Profile မရှိတော့ဘူးနော်။",show_alert=True)
        return
    await q.answer()
    await q.message.reply_text(f"💌 <b>{html.escape(source['display_name'])}</b> က <b>{html.escape(target['display_name'])}</b> ဆီ မိတ်ဆက်ခွင့် တကယ်တောင်းမလား?",
        parse_mode="HTML", reply_to_message_id=q.message.message_id,
        reply_markup=K([[B("💌 သေချာပို့မယ်",callback_data=f"intro_confirm:{sender_id}:{gid}:{target_id}")],
                        [B("🌷 မပို့တော့ဘူး",callback_data=f"intro_cancel:{sender_id}:{gid}:{target_id}")]]))


async def intro_confirm_callback(update, context):
    q = update.callback_query
    try:
        verb, sender_text, gid_text, target_text = q.data.split(":")
        sender_id, gid, target_id = map(int,(sender_text,gid_text,target_text))
    except (ValueError,AttributeError):
        await q.answer("မိတ်ဆက်ကတ်လေး အဆင်မပြေတော့ဘူး။",show_alert=True)
        return
    if q.from_user.id != sender_id or q.message.chat.id != gid:
        await q.answer("ဖိတ်ခေါ်စာပိုင်ရှင်ပဲ ဆုံးဖြတ်နိုင်တယ်နော်။",show_alert=True)
        return
    if verb == "intro_cancel":
        await q.answer()
        await q.edit_message_text("🌷 ဒီဖိတ်ခေါ်စာလေး မပို့တော့ဘူးနော်။")
        return
    options = await db.group_settings(gid)
    if not options["requests"] or not options["intros"]:
        await q.answer("Group မှာ ဖိတ်ခေါ်ခွင့် ခဏပိတ်ထားတယ်နော်။",show_alert=True)
        return
    if not await member(context.bot,gid,sender_id) or not await member(context.bot,gid,target_id):
        await q.answer("Group အဖွဲ့ဝင်အခြေအနေ ပြောင်းသွားပြီနော်။",show_alert=True)
        return
    source = await db.get_profile(sender_id,gid)
    target = await db.get_profile(target_id,gid)
    if not source or not target:
        await q.answer("Profile လေး မရှိတော့ဘူးနော်။",show_alert=True)
        return
    result = await db.send_request(sender_id,gid,target_id,gid)
    if not result:
        await q.answer("ဖိတ်ခေါ်ပြီးသား ဒါမှမဟုတ် ခဏစောင့်ဖို့လိုနေတယ်နော်။",show_alert=True)
        return
    await q.answer("💌 ဖိတ်ခေါ်စာ ပို့လိုက်ပြီ")
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass
    try:
        card = await show_profile(context.bot,gid,source,
            K([[B("💕 အဖြေပေးမယ်",callback_data=f"reply:{result['id']}:{target_id}")]]),
            header=request_card_title(
                source,target,result["id"],recipient_id=target_id,
                username=await request_recipient_username(context.bot,gid,target_id)),
            reply_to_message_id=getattr(getattr(q.message,"reply_to_message",None),"message_id",None))
        await db.remember_request_group_message(result["id"],target_id,"card",card.message_id)
    except TelegramError:
        logging.exception("Intro request persisted but delivery failed")


SETTING_LABELS = {
    "matchmaking": "💗 ဆုံတွေ့ခွင့်", "registration": "📝 မိတ်ဆက်ကတ် စာရင်းသွင်းခွင့်",
    "requests": "💌 ဖိတ်ခေါ်စာပို့ခွင့်", "public_browse": "🌍 အများမြင်ကတ် လှည့်ကြည့်ခွင့်",
    "intros": "🎀 မိတ်ဆက်ကတ် တင်ခွင့်", "cleanup": "🧹 ကတ်ဟောင်း ရှင်းလင်းခွင့်",
}

async def is_admin(bot, group_id, user_id):
    try:
        status = (await bot.get_chat_member(group_id, user_id)).status
        return status in ("administrator", "creator")
    except TelegramError:
        return False

def settings_buttons(row):
    return K([[B(f"{'✅' if row[name] else '🚫'} {label}",
                 callback_data=f"setting:{row['group_id']}:{name}")]
              for name, label in SETTING_LABELS.items()])

async def settings(update, context):
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("🌷 /settings ကို Group ထဲမှာပဲ ဖွင့်နိုင်တယ်နော်။")
        return
    gid, uid = update.effective_chat.id, update.effective_user.id
    if not await is_admin(context.bot, gid, uid):
        await update.message.reply_text("💗 ဒီအပြင်အဆင်လေးကို Group Admin တွေပဲ ပြောင်းနိုင်တယ်နော်။")
        return
    row = await db.group_settings(gid)
    await update.message.reply_text("🎀 <b>လူတောင်းပွဲ Group Settings</b>\nဖွင့်/ပိတ်ချင်တာလေးကို နှိပ်ပေးပါနော်။",
        parse_mode="HTML", reply_markup=settings_buttons(row))

async def setting_callback(update, context):
    q = update.callback_query
    try:
        _, group_id, name = q.data.split(":")
        gid = int(group_id)
    except (ValueError, AttributeError):
        await q.answer("ခလုတ်လေး အဆင်မပြေတော့ဘူးနော်။", show_alert=True)
        return
    if (q.message.chat.id != gid or q.message.chat.type not in ("group", "supergroup")
            or name not in SETTING_LABELS):
        await q.answer("ဒီ Settings ခလုတ်လေး မမှန်တော့ဘူးနော်။", show_alert=True)
        return
    if not await is_admin(context.bot, gid, q.from_user.id):
        await q.answer("Group Admin တွေပဲ ပြောင်းနိုင်တယ်နော်။", show_alert=True)
        return
    current = await db.group_settings(gid)
    row = await db.set_group_setting(gid, name, not current[name])
    await q.answer("✅ အပြင်အဆင် သိမ်းထားပြီ")
    await q.edit_message_reply_markup(reply_markup=settings_buttons(row))

async def membership_change(update, context):
    """Archive a departing adult's profile; restore on return without discarding data."""
    event = update.chat_member
    if not event or event.chat.type not in ("group","supergroup"):
        return
    target = event.new_chat_member.user
    if target.is_bot:
        return
    old, new = event.old_chat_member.status, event.new_chat_member.status
    gone = ("left", "kicked")
    active = ("member", "administrator", "creator")
    try:
        if new in gone and old not in gone:
            await db.archive_profile(target.id,event.chat.id)
        elif new in active and old in gone:
            await db.restore_profile(target.id,event.chat.id)
    except Exception:
        logging.exception("Could not update profile archive status")

def handlers():
    registration = ConversationHandler(
        entry_points=[CommandHandler("start", start, filters.ChatType.PRIVATE)],
        states={
            CONFIRM_AGE: [CallbackQueryHandler(confirm_age, pattern=r"^age_confirm:(yes|no)$")],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_step)],
            MEDIA: [MessageHandler(filters.PHOTO | filters.VIDEO, media_step)],
            BIO: [CommandHandler("skip", bio_step), MessageHandler(filters.TEXT & ~filters.COMMAND, bio_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    profile_editor = ConversationHandler(
        entry_points=[CallbackQueryHandler(profile_edit_begin,pattern=r"^profile_edit:")],
        states={EDIT_TEXT:[CommandHandler("skip",profile_edit_text),
                           MessageHandler(filters.TEXT & ~filters.COMMAND,profile_edit_text)],
                EDIT_MEDIA:[MessageHandler(filters.PHOTO | filters.VIDEO,profile_edit_media)]},
        fallbacks=[CommandHandler("cancel",profile_edit_cancel)],
        allow_reentry=True,
    )
    reason_editor = ConversationHandler(
        entry_points=[CallbackQueryHandler(reason_start,pattern=r"^reason_start:")],
        states={REJECTION_TEXT:[MessageHandler(filters.TEXT & ~filters.COMMAND,reason_text)]},
        fallbacks=[CommandHandler("cancel",reason_cancel)],
        allow_reentry=True,
    )
    owner_setup = ConversationHandler(
        entry_points=[CommandHandler("owner",owner_panel),
                      CallbackQueryHandler(owner_change_group,pattern=r"^owner:enter_group$")],
        states={OWNER_GROUP_INPUT:[MessageHandler(filters.TEXT & ~filters.COMMAND,owner_group_input)]},
        fallbacks=[CommandHandler("cancel",owner_group_cancel)],
        allow_reentry=True,
    )
    return [registration, profile_editor, reason_editor, owner_setup,
            CallbackQueryHandler(owner_callback,pattern=r"^owner:"), ChatMemberHandler(membership_change,ChatMemberHandler.CHAT_MEMBER), CommandHandler("register", register), CommandHandler("match", match),
            CallbackQueryHandler(browse_callback, pattern=r"^browse:"),
            CallbackQueryHandler(browse_mode_callback, pattern=r"^browse_mode:"),
            CallbackQueryHandler(ask_callback, pattern=r"^ask:"),
            CallbackQueryHandler(ask_confirm_callback, pattern=r"^ask_(confirm:|cancel:)"), CallbackQueryHandler(reply_callback, pattern=r"^reply:"),
            CallbackQueryHandler(decide_callback, pattern=r"^decide:"),
            CommandHandler("inbox", inbox), CommandHandler("outgoing", outgoing),
            CommandHandler("profile", profile), CommandHandler("settings", settings),
            CallbackQueryHandler(setting_callback, pattern=r"^setting:"),
            CallbackQueryHandler(home_callback, pattern=r"^home:"),
            CallbackQueryHandler(profile_view, pattern=r"^profile_view:"),
            CallbackQueryHandler(profile_public, pattern=r"^profile_public:"),
            CallbackQueryHandler(profile_delete_ask,pattern=r"^profile_delete_ask:"),
            CallbackQueryHandler(profile_delete_do,pattern=r"^profile_delete_(do:|cancel$)"),
            CallbackQueryHandler(intro_callback,pattern=r"^intro_(yes:|skip$)"),
            CallbackQueryHandler(reason_start,pattern=r"^reason_skip$"),
            CallbackQueryHandler(reason_finish,pattern=r"^reason_(send|cancel)$"),
            CallbackQueryHandler(intro_view,pattern=r"^intro_view:"),
            CallbackQueryHandler(intro_confirm_callback,pattern=r"^intro_(confirm:|cancel:)"),
            CallbackQueryHandler(inbox_open, pattern=r"^inbox_open:"),
            CallbackQueryHandler(withdraw_ask, pattern=r"^withdraw_ask:"),
            CallbackQueryHandler(withdraw_do, pattern=r"^withdraw_(do:|cancel$)")]
