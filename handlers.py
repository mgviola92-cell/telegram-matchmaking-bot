"""Group-specific registration and browsing handlers. No background database polling."""
import html
import logging
from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, InputMediaPhoto, InputMediaVideo
from telegram.error import TelegramError
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
import repository as db
from responses import say

CONFIRM_AGE, NAME, AGE, MEDIA, BIO = range(5)
drafts = {}

def caption(p):
    return f"💗 <b>{html.escape(p['display_name'])}</b> · {p['age']} နှစ်\n\n{html.escape(p['bio'] or 'စကားလေးတွေ ပြောကြည့်ရအောင် 💌')}"

async def member(bot, group_id, user_id):
    try:
        m = await bot.get_chat_member(group_id, user_id)
        return m.status not in ("left", "kicked")
    except TelegramError:
        return False

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
        return ConversationHandler.END
    if args and args[0].startswith("join_"):
        try:
            gid = int(args[0][5:])
        except ValueError:
            await msg.reply_text("ဒီလင့်ခ်လေး အဆင်မပြေတော့ဘူးနော်။")
            return ConversationHandler.END
        if not await member(context.bot, gid, update.effective_user.id):
            await msg.reply_text("အဲဒီ Group ထဲမှာ အရင်ဝင်ထားဖို့ လိုတယ်နော် 💗")
            return ConversationHandler.END
        drafts[update.effective_user.id] = {"group_id": gid}
        await msg.reply_text("💌 လူတောင်းပွဲမှာ ပါဝင်ဖို့ အသက် ၁၈ နှစ် ပြည့်ပြီးပြီလား?", reply_markup=K([[B("💗 ပြည့်ပြီးပါပြီ", callback_data="age_confirm:yes")], [B("🌷 မပြည့်သေးပါဘူး", callback_data="age_confirm:no")]]))
        return CONFIRM_AGE
    await msg.reply_text(say("welcome", update.effective_user.id))
    return ConversationHandler.END

async def register(update, context):
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("💗 Group ထဲမှာ /register လို့ ရေးပေးပါနော်။")
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
    await update.message.reply_text("အသက်လေး ဘယ်နှနှစ်ရှိပြီလဲ?")
    return AGE

async def age_step(update, context):
    try:
        age = int(update.message.text.strip())
    except ValueError:
        age = 0
    if not 18 <= age <= 120:
        await update.message.reply_text("အသက် ၁၈ နှစ်ပြည့်ပြီးသူတွေအတွက်ပဲ ဖွင့်ထားတာနော်။ အသက်ကို ပြန်စစ်ပေးပါဦး 💗")
        return AGE
    if not drafts.get(update.effective_user.id, {}).get("adult_confirmed"):
        await update.message.reply_text("💌 /register နဲ့ ပြန်စလိုက်နော်။")
        return ConversationHandler.END
    drafts[update.effective_user.id]["age"] = age
    await update.message.reply_text("📸 ဓာတ်ပုံတစ်ပုံ ဒါမှမဟုတ် Video တိုလေးတစ်ခု ပို့ပေးပါ။")
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
    if not d.get("adult_confirmed") or d.get("age", 0) < 18:
        drafts.pop(update.effective_user.id, None)
        await update.message.reply_text("💌 /register နဲ့ ပြန်စလိုက်နော်။")
        return ConversationHandler.END
    bio = "" if update.message.text == "/skip" else update.message.text[:300]
    await db.upsert_profile(update.effective_user.id, d["group_id"], d["name"], d["age"], d["media_type"], d["file_id"], bio)
    drafts.pop(update.effective_user.id, None)
    await update.message.reply_text("💖 Profile လေး သိမ်းပြီးပြီ။ Group ထဲမှာ /match နဲ့ စလှည့်ကြည့်လို့ရပြီနော်။")
    return ConversationHandler.END

async def cancel(update, context):
    drafts.pop(update.effective_user.id, None)
    await update.message.reply_text("နောက်မှ ပြန်လုပ်လို့ရပါတယ်နော် 💗")
    return ConversationHandler.END

async def show_profile(bot, chat_id, p, keyboard):
    kw = {"caption": caption(p), "parse_mode": "HTML", "reply_markup": keyboard}
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
        await update.message.reply_text("💗 မိတ်ဆက်ကတ်လေး ဖွင့်ထားပြီးသားနော်။ အပေါ်က ကတ်လေးမှာ ဆက်လှည့်ကြည့်လိုက်ပါဦး။")
        return
    results = await db.browse_profiles(uid, gid, public=False, limit=50)
    if not results:
        await update.message.reply_text(say("no_matches", uid))
        return
    p = results[0]
    sent = await show_profile(context.bot, gid, p, match_buttons(uid,gid,p,0,len(results),False))
    keys = [[row["user_id"],row["group_id"]] for row in results]
    await db.save_browse_session(uid,gid,sent.message_id,False,keys)


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
    if not keys:
        await q.answer("လှည့်ကြည့်ဖို့ Profile မရှိတော့ဘူးနော်။", show_alert=True)
        return
    if delta > 0 and session["position"] == len(keys)-1:
        await q.answer("💗 နောက်ဆုံးကတ်လေးအထိ ရောက်နေပြီနော်။")
    elif delta < 0 and session["position"] == 0:
        await q.answer("🌷 ပထမဆုံးကတ်လေးအထိ ရောက်နေပြီနော်။")
    else:
        await q.answer()
    key = keys[session["position"]]
    p = await db.get_profile(key[0],key[1])
    if not p:
        await q.answer("ဒီ Profile လေး မရှိတော့ဘူးနော်။", show_alert=True)
        return
    try:
        await edit_browse_card(q,uid,gid,p,session["position"],len(keys),session["public_mode"])
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
    await q.answer("🌍 Public Browse" if public else "🏡 Group Only")
    try:
        await edit_browse_card(q,uid,gid,results[0],0,len(results),public)
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
    result = await db.send_request(invoker, source_group, target_user, target_group)
    if not result:
        await q.answer("အချစ်စာလေး ပို့ထားပြီးသား ဖြစ်နိုင်ပါတယ် 💌", show_alert=True)
        return
    await q.answer("အချစ်စာလေး ပို့လိုက်ပြီ 💌")
    try:
        await context.bot.send_message(source_group, say("request_sent", invoker))
        await show_profile(context.bot, target_group, source, K([[B("💌 အဖြေပေးမယ်", callback_data=f"reply:{result['id']}:{target_user}")]]))
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
    me = await context.bot.get_me()
    await q.answer()
    await q.message.reply_text("💌 အဖြေပေးဖို့ Private Chat ထဲ ဝင်ခဲ့နော်။", reply_markup=K([[B("💗 အဖြေပေးမယ်", url=f"https://t.me/{me.username}?start=reply_{request_id}")]]))

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
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        logging.exception("Could not disable answered request buttons")
    sender_id, recipient_id = result["sender_id"], result["recipient_id"]
    if action == "rejected":
        await q.message.reply_text("🌷 ဒီတစ်ခေါက်တော့ မိတ်ဆက်ခွင့်လေးကို ငြင်းလိုက်ပြီနော်။")
        try:
            await context.bot.send_message(sender_id, "💌 ပို့ထားတဲ့ မိတ်ဆက်ဖိတ်ခေါ်ချက်လေးကို တစ်ဖက်က လက်မခံခဲ့ဘူးနော်။")
        except TelegramError:
            logging.info("Sender private chat unavailable for rejection notice")
        return
    a = f'<a href="tg://user?id={sender_id}">မိတ်ဆက်ဖိတ်ခေါ်သူ</a>'
    b = f'<a href="tg://user?id={recipient_id}">လက်ခံသူ</a>'
    announcement = f"💕 <b>လူတောင်းပွဲမှာ ဆုံတွေ့မှုလေးတစ်ခု ဖြစ်သွားပြီ!</b>\n{a} နဲ့ {b} တို့ မိတ်ဆက်ခွင့်ရသွားပြီနော် 💌"
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


async def inbox(update, context):
    """Private, unified newest-first incoming requests; no polling."""
    if update.effective_chat.type != "private":
        await update.message.reply_text("💌 အချစ်စာဝင်ပုံးကို Private Chat မှာ ဖွင့်ကြည့်ပေးနော်။")
        return
    items = await db.incoming_requests(update.effective_user.id)
    if not items:
        await update.message.reply_text("🌷 အခုအချိန်မှာ အဖြေစောင့်နေတဲ့ အချစ်စာလေး မရှိသေးဘူးနော်။")
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
    await show_profile(context.bot, q.from_user.id, sender,
        K([[B("💕 လက်ခံမယ်", callback_data=f"decide:{request_id}:accepted")],
           [B("💔 ငြင်းမယ်", callback_data=f"decide:{request_id}:rejected")]]))

async def outgoing(update, context):
    if update.effective_chat.type != "private":
        await update.message.reply_text("💌 ပို့ထားတဲ့ စာလေးတွေကို Private Chat မှာ ကြည့်ပေးနော်။")
        return
    items = await db.outgoing_requests(update.effective_user.id)
    if not items:
        await update.message.reply_text("💗 လောလောဆယ် အဖြေစောင့်နေတဲ့ ဖိတ်ခေါ်စာ မရှိသေးဘူးနော်။")
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
    await q.message.reply_text("💌 ဒီဖိတ်ခေါ်စာလေးကို တကယ် ပြန်ရုပ်သိမ်းမလား?",
        reply_markup=K([[B("💔 ပြန်ရုပ်သိမ်းမယ်", callback_data=f"withdraw_do:{rid}")],
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
    await q.edit_message_text("🌷 ဖိတ်ခေါ်စာလေးကို ပြန်ရုပ်သိမ်းပြီးပါပြီ။")


async def profile(update, context):
    """List own profiles in private; public selection is opt-in."""
    if update.effective_chat.type != "private":
        await update.message.reply_text("💗 Profile လေးတွေကို Private Chat မှာပဲ စီမံကြမယ်နော်။")
        return
    rows = await db.user_profiles(update.effective_user.id)
    if not rows:
        await update.message.reply_text("🌷 Profile လေး မရှိသေးဘူးနော်။ Group ထဲက /register နဲ့ စကြမယ်။")
        return
    buttons = []
    for row in rows:
        label = ("🌍 " if row["is_public"] else "💗 ") + row["display_name"][:25]
        buttons.append([B(label, callback_data=f"profile_view:{row['group_id']}")])
    await update.message.reply_text(
        f"💗 <b>ကိုယ့် Profile လေးများ</b>\nProfile {len(rows)} ခု ရှိတယ်နော်။ 🌍 ဆိုတာ Public ဖွင့်ထားတဲ့ Profile ပါ။",
        parse_mode="HTML", reply_markup=K(buttons))

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
    public = bool(p["is_public"])
    toggle = B("🌷 Public ပိတ်မယ်" if public else "🌍 Public ဖွင့်မယ်",
               callback_data=f"profile_public:{group_id}:{0 if public else 1}")
    await show_profile(context.bot, q.from_user.id, p, K([[toggle]]))

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
    await q.edit_message_reply_markup(reply_markup=K([[
        B("🌷 Public ပိတ်မယ်" if state else "🌍 Public ဖွင့်မယ်",
          callback_data=f"profile_public:{gid}:{0 if state else 1}")
    ]]))


SETTING_LABELS = {
    "matchmaking": "💗 Matchmaking", "registration": "📝 Registration",
    "requests": "💌 Requests", "public_browse": "🌍 Public Browse",
    "intros": "🎀 မိတ်ဆက်ကတ်", "cleanup": "🧹 Cleanup",
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
    await update.message.reply_text("🎀 <b>လူတောင်းပွဲ Group Settings</b>\\nဖွင့်/ပိတ်ချင်တာလေးကို နှိပ်ပေးပါနော်။",
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

def handlers():
    registration = ConversationHandler(
        entry_points=[CommandHandler("start", start, filters.ChatType.PRIVATE)],
        states={
            CONFIRM_AGE: [CallbackQueryHandler(confirm_age, pattern=r"^age_confirm:(yes|no)$")],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_step)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age_step)],
            MEDIA: [MessageHandler(filters.PHOTO | filters.VIDEO, media_step)],
            BIO: [CommandHandler("skip", bio_step), MessageHandler(filters.TEXT & ~filters.COMMAND, bio_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    return [registration, CommandHandler("register", register), CommandHandler("match", match),
            CallbackQueryHandler(browse_callback, pattern=r"^browse:"),
            CallbackQueryHandler(browse_mode_callback, pattern=r"^browse_mode:"),
            CallbackQueryHandler(ask_callback, pattern=r"^ask:"), CallbackQueryHandler(reply_callback, pattern=r"^reply:"),
            CallbackQueryHandler(decide_callback, pattern=r"^decide:"),
            CommandHandler("inbox", inbox), CommandHandler("outgoing", outgoing),
            CommandHandler("profile", profile), CommandHandler("settings", settings),
            CallbackQueryHandler(setting_callback, pattern=r"^setting:"),
            CallbackQueryHandler(profile_view, pattern=r"^profile_view:"),
            CallbackQueryHandler(profile_public, pattern=r"^profile_public:"),
            CallbackQueryHandler(inbox_open, pattern=r"^inbox_open:"),
            CallbackQueryHandler(withdraw_ask, pattern=r"^withdraw_ask:"),
            CallbackQueryHandler(withdraw_do, pattern=r"^withdraw_(do:|cancel$)")]
