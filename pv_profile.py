"""Telegram-native PV profile management with ReplyKeyboardMarkup.

Private-only, one global profile per user. Navigation state lives in the
user's private conversation context, never in a group or another user's chat.
"""
import logging
from telegram import ReplyKeyboardMarkup
from telegram.error import TelegramError
import repository as db
import pv_matching

NAME="✏️ နာမည်ပြင်မယ်"
AGE="🎲 ဂဏန်းပြင်မယ်"
CITY="🏙 မြို့/တိုင်းပြင်မယ်"
BIO="💬 Bio ပြင်မယ်"
MEDIA="📸 ပုံ/Video ပြင်မယ်"
SHARE="📣 Group မှာ မိတ်ဆက်မယ်"
DELETE="🗑 Profile ဖျက်မယ်"
BACK="⬅️ နောက်ပြန်"
HOME="🏠 ပင်မ Menu"
CONFIRM="🗑 သေချာဖျက်မယ်"
CANCEL="🌷 မဖျက်တော့ဘူး"
SKIP="🌷 မဖော်ပြတော့ဘူး"
MENU=ReplyKeyboardMarkup([[NAME,AGE],[CITY,BIO],[MEDIA,SHARE],[DELETE,HOME]],resize_keyboard=True,is_persistent=True)
EDIT_MENU=ReplyKeyboardMarkup([[SKIP],[BACK,HOME]],resize_keyboard=True,is_persistent=True)
MEDIA_MENU=ReplyKeyboardMarkup([[BACK,HOME]],resize_keyboard=True,is_persistent=True)
DELETE_MENU=ReplyKeyboardMarkup([[CONFIRM,CANCEL],[HOME]],resize_keyboard=True,is_persistent=True)
ACTIONS={NAME:"display_name",AGE:"age",CITY:"location",BIO:"bio",MEDIA:"media"}


async def open_profile(update,context):
    if update.effective_chat.type!="private":
        return
    uid=update.effective_user.id
    profiles=await db.user_profiles(uid)
    if not profiles:
        await update.effective_message.reply_text(
            "🌷 Profile မရှိသေးဘူးနော်။ Bot ရှိတဲ့ Group မှာ /register နဲ့ စတင်နိုင်တယ်။",
            reply_markup=pv_matching.MAIN_KEYBOARD)
        return
    p=profiles[0]
    context.user_data["pv_profile"]={"mode":"menu","group_id":p["group_id"]}
    from handlers import show_profile,match_caption
    card=await show_profile(context.bot,uid,p,None,full_caption=await match_caption(context.bot,p))
    context.user_data["pv_profile"]["card_message_id"]=card.message_id
    await update.effective_message.reply_text(
        "🎀 ကိုယ့် Profile ကို ဒီအောက်က ခလုတ်လေးတွေနဲ့ ပြင်ဆင်နိုင်ပြီနော်။",
        reply_markup=MENU)


async def respond(update,context):
    if update.effective_chat.type!="private":
        return False
    state=context.user_data.get("pv_profile")
    if not state:
        return False
    text=update.effective_message.text
    uid=update.effective_user.id
    if text==HOME:
        context.user_data.pop("pv_profile",None)
        await update.effective_message.reply_text(
            "💗 ပင်မ Menu ကို ပြန်ရောက်ပြီနော်။",reply_markup=pv_matching.MAIN_KEYBOARD)
        return True
    if text==BACK:
        state["mode"]="menu"
        state.pop("field",None)
        await update.effective_message.reply_text(
            "🎀 Profile ပြင်ဆင်ဖို့ ခလုတ်လေးတွေ ပြန်ရွေးနိုင်ပြီနော်။",reply_markup=MENU)
        return True
    p=await db.get_profile(uid,state["group_id"])
    if not p:
        context.user_data.pop("pv_profile",None)
        await update.effective_message.reply_text(
            "🌷 Profile မရှိတော့ဘူးနော်။",reply_markup=pv_matching.MAIN_KEYBOARD)
        return True
    mode=state["mode"]
    if mode=="menu":
        if text==SHARE:
            from handlers import member,REG_INTRO_KEYBOARD
            settings=await db.group_settings(state["group_id"])
            if not settings["intros"] or not await member(
                context.bot,state["group_id"],uid):
                await update.effective_message.reply_text(
                    "🌷 ဒီ Group မှာ မိတ်ဆက်ကတ် မပို့နိုင်သေးဘူးနော်။",
                    reply_markup=MENU)
                return True
            context.user_data["pv_intro_choice_gid"]=state["group_id"]
            await update.effective_message.reply_text(
                "📣 ကိုယ့် Profile ကို Group မှာ မိတ်ဆက်ကတ်တင်မလား?",
                reply_markup=REG_INTRO_KEYBOARD)
            return True
        if text==DELETE:
            state["mode"]="delete"
            await update.effective_message.reply_text(
                "🗑 ဒီ Profile ကို တကယ်ဖျက်မလား? ဖျက်ပြီးရင် ပြန်ယူလို့မရတော့ဘူးနော်။",
                reply_markup=DELETE_MENU)
            return True
        field=ACTIONS.get(text)
        if not field:
            return False
        state["mode"]="edit"
        state["field"]=field
        hints={"display_name":"💗 နာမည်အသစ်ကို ရေးပေးနော်။",
               "age":"🎲 Profile မှာပြချင်တဲ့ ဂဏန်းကို ရေးပေးနော်။",
               "location":"🏙 မြို့/တိုင်းပဲ ရေးပေးနော်။ လိပ်စာအတိအကျ မရေးပါနဲ့။",
               "bio":"💬 Bio အသစ်လေး ရေးပေးနော်။",
               "media":"📸 ပုံအသစ် ဒါမှမဟုတ် စက္ကန့် ၃၀ အောက် Video ပို့ပေးနော်။"}
        await update.effective_message.reply_text(
            hints[field],reply_markup=MEDIA_MENU if field=="media" else EDIT_MENU)
        return True
    if mode=="delete":
        if text==CANCEL:
            state["mode"]="menu"
            await update.effective_message.reply_text(
                "💗 Profile ကို ဆက်သိမ်းထားမယ်နော်။",reply_markup=MENU)
            return True
        if text!=CONFIRM:
            return True
        result=await db.delete_profile(uid,state["group_id"])
        context.user_data.pop("pv_profile",None)
        from profile_cleanup import cleanup_deleted_profile
        await cleanup_deleted_profile(context.bot,uid,result,
            own_card_id=state.get("card_message_id"))
        await update.effective_message.reply_text(
            "🗑 Profile ကို ဖျက်ပြီးပြီနော်။" if result else "🌷 Profile မရှိတော့ဘူးနော်။",
            reply_markup=pv_matching.MAIN_KEYBOARD)

        return True
    if mode!="edit" or text in (NAME,AGE,CITY,BIO,MEDIA,DELETE,SHARE):
        return False
    field=state["field"]
    if field=="media":
        return False
    if field=="display_name":
        value=text.strip()
        if not 1<=len(value)<=60:
            await update.effective_message.reply_text("🌷 နာမည်ကို စာလုံး ၁–၆၀ အတွင်း ရေးပေးနော်။")
            return True
    elif field=="age":
        try: value=int(text.strip())
        except ValueError: value=0
        if not 0<=value<=999999999 or not text.strip().isdecimal():
            await update.effective_message.reply_text("🌷 0 ကနေ 999999999 အတွင်း ဂဏန်းပဲ ရေးပေးနော်။")
            return True
    else:
        limit=300 if field=="bio" else 50
        value="" if text==SKIP else text.strip()
        if len(value)>limit or any(x in value for x in ("\n","\r")) and field=="location":
            await update.effective_message.reply_text(f"🌷 စာလုံး {limit} အတွင်း ပြန်ရေးပေးနော်။")
            return True
    result=await db.update_profile_text(uid,state["group_id"],field,value)
    state["mode"]="menu"
    state.pop("field",None)
    await update.effective_message.reply_text(
        "💗 Profile လေး ပြင်ပြီးပြီနော်။" if result else "🌷 Profile မရှိတော့ဘူးနော်။",
        reply_markup=MENU)
    return True


async def handle_media(update,context):
    if update.effective_chat.type!="private":
        return
    state=context.user_data.get("pv_profile")
    if not state or state.get("mode")!="edit" or state.get("field")!="media":
        return
    msg=update.effective_message
    if msg.photo:
        kind,fid="photo",msg.photo[-1].file_id
    elif msg.video and msg.video.duration is not None and msg.video.duration<=30:
        kind,fid="video",msg.video.file_id
    else:
        await msg.reply_text("🌷 ဓာတ်ပုံ ဒါမှမဟုတ် ၃၀ စက္ကန့်အောက် Video ပို့ပေးနော်။")
        return
    result=await db.update_profile_media(update.effective_user.id,state["group_id"],kind,fid)
    state["mode"]="menu"
    state.pop("field",None)
    await msg.reply_text("📸 Profile ပုံအသစ် ပြောင်းပြီးပြီနော်။" if result else
                         "🌷 Profile မရှိတော့ဘူးနော်။",reply_markup=MENU)
