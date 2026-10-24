"""Group-specific registration and browsing handlers. No background database polling."""
import html
import logging
from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K
from telegram.error import TelegramError
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
import repository as db

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
        await msg.reply_text("💘 လူတောင်းပွဲက ကြိုဆိုပါတယ်။ /match နဲ့ လှည့်ကြည့်နိုင်ပါတယ်။")
        return
    args = context.args
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
    await msg.reply_text("💘 လူတောင်းပွဲက ကြိုဆိုပါတယ်။ Group ထဲက /register ကိုနှိပ်ပြီး ကိုယ့် Profile လေး စလုပ်နိုင်ပါတယ်။")
    return ConversationHandler.END

async def register(update, context):
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("💗 Group ထဲမှာ /register လို့ ရေးပေးပါနော်။")
        return
    me = await context.bot.get_me()
    url = f"https://t.me/{me.username}?start=join_{update.effective_chat.id}"
    await update.message.reply_text("💌 ကိုယ့်အကြောင်းလေး မိတ်ဆက်ဖို့ အောက်ကနေ ဝင်ခဲ့နော်။", reply_markup=K([[B("💗 Profile လေး ဖန်တီးမယ်", url=url)]]))

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
    elif msg.video and msg.video.duration <= 30:
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
    d = drafts.pop(update.effective_user.id, None)
    if not d:
        return ConversationHandler.END
    if not await member(context.bot, d["group_id"], update.effective_user.id):
        await update.message.reply_text("Group ထဲမှာ မရှိတော့လို့ Profile မသိမ်းထားဘူးနော်။")
        return ConversationHandler.END
    if not d.get("adult_confirmed") or d.get("age", 0) < 18:
        await update.message.reply_text("💌 /register နဲ့ ပြန်စလိုက်နော်။")
        return ConversationHandler.END
    bio = "" if update.message.text == "/skip" else update.message.text[:300]
    await db.upsert_profile(update.effective_user.id, d["group_id"], d["name"], d["age"], d["media_type"], d["file_id"], bio)
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
    own = await db.get_profile(uid, gid)
    if not own:
        me = await context.bot.get_me()
        url = f"https://t.me/{me.username}?start=join_{gid}"
        await update.message.reply_text("💌 လှည့်ကြည့်ဖို့ ကိုယ့် Profile လေး အရင်မိတ်ဆက်ရအောင်နော်။", reply_markup=K([[B("💗 Profile လေး ဖန်တီးမယ်", url=url)]]))
        return
    results = await db.browse_profiles(uid, gid, public=False, limit=50)
    if not results:
        await update.message.reply_text("💌 ဒီ Group ထဲမှာ လှည့်ကြည့်ဖို့ Profile လေးတွေ မရှိသေးဘူး။")
        return
    p = results[0]
    keyboard = K([[B("💌 တောင်းမယ်", callback_data=f"ask:{uid}:{gid}:{p['user_id']}:{p['group_id']}")]])
    await show_profile(context.bot, gid, p, keyboard)

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
    result = await db.send_request(invoker, source_group, target_user, target_group)
    if not result:
        await q.answer("အချစ်စာလေး ပို့ထားပြီးသား ဖြစ်နိုင်ပါတယ် 💌", show_alert=True)
        return
    await q.answer("အချစ်စာလေး ပို့လိုက်ပြီ 💌")
    try:
        await context.bot.send_message(source_group, "💌 အချစ်စာလေး ပို့ပြီးပြီနော်။")
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
            CallbackQueryHandler(ask_callback, pattern=r"^ask:"), CallbackQueryHandler(reply_callback, pattern=r"^reply:")]
