"""Private-chat matching with Telegram ReplyKeyboardMarkup.

Started from a verified group deep link; never public group browsing and
never uses group messages as the session card. DB holds IDs and cursor only.
"""
import asyncio
import html
import json
import logging
from datetime import datetime, timezone
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from db import pool
import repository as db

SKIP = "👎 ကျော်မယ်"
REQUEST = "💌 တောင်းမယ်"
STOP = "❌ ပွဲသိမ်းမယ်"
KEYBOARD = ReplyKeyboardMarkup([[SKIP, REQUEST], [STOP]], resize_keyboard=True)
_tasks = {}


def request_quotes(sender, recipient, request_id, source, target, *, sender_id, recipient_id, sender_side):
    """Different user mention visibility per group, same two quote sections."""
    from handlers import nickname_link
    # Sender account is disclosed in their own source group only.
    left = nickname_link(sender["display_name"], sender_id if sender_side else None)
    right = nickname_link(recipient["display_name"], None if sender_side else recipient_id)
    return (f"<blockquote>💌 {left} → {right} · #{int(request_id)}</blockquote>\n"
            f"\u200b\n<blockquote>🏡 Group - {source} → {target}</blockquote>")


async def get_session(user_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""SELECT * FROM pv_match_sessions
            WHERE user_id=$1 AND updated_at>now()-interval '3 minutes'""",user_id)


async def save_session(user_id, group_id, message_id, keys):
    p = await pool()
    async with p.acquire() as c:
        await c.execute("""INSERT INTO pv_match_sessions
            (user_id,source_group_id,card_message_id,profile_keys,position,updated_at)
            VALUES($1,$2,$3,$4::jsonb,0,now())
            ON CONFLICT(user_id) DO UPDATE SET
            source_group_id=excluded.source_group_id,
            card_message_id=excluded.card_message_id,
            profile_keys=excluded.profile_keys,
            position=0,updated_at=now()""",
            user_id,group_id,message_id,json.dumps(keys))


async def set_position(user_id, old_message_id, position, new_message_id=None):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""UPDATE pv_match_sessions
            SET position=$3,card_message_id=COALESCE($4,card_message_id),updated_at=now()
            WHERE user_id=$1 AND card_message_id=$2
            AND updated_at>now()-interval '3 minutes'
            RETURNING *""",user_id,old_message_id,position,new_message_id)


async def finish(user_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("DELETE FROM pv_match_sessions WHERE user_id=$1 RETURNING *",user_id)


async def retire(bot, user_id, card_id):
    try:
        await bot.delete_message(chat_id=user_id,message_id=card_id)
        return True
    except TelegramError:
        logging.info("PV profile delete unavailable for user %s",user_id)
        return False


def profile_key(session):
    keys=session["profile_keys"]
    if isinstance(keys,str):
        keys=json.loads(keys)
    if not keys or session["position"] >= len(keys):
        return None
    return keys[session["position"]]


async def expire(bot,user_id,card_id,seconds=180):
    try:
        await asyncio.sleep(max(0,seconds)+0.3)
        p=await pool()
        async with p.acquire() as c:
            row=await c.fetchrow("""DELETE FROM pv_match_sessions
                WHERE user_id=$1 AND card_message_id=$2 AND
                      updated_at<=now()-interval '3 minutes'
                RETURNING card_message_id""",user_id,card_id)
        if row:
            await retire(bot,user_id,card_id)
            try:
                await bot.send_message(user_id,"🌷 ဒီတစ်ခေါက်ကြည့်တာလေး နားလိုက်ပြီနော်။",
                                       reply_markup=ReplyKeyboardRemove())
            except TelegramError:
                pass
    except asyncio.CancelledError:
        return
    except Exception:
        logging.exception("PV session timeout failure")
    finally:
        if _tasks.get(user_id) is asyncio.current_task():
            _tasks.pop(user_id,None)


def reset_timeout(bot,user_id,card_id):
    old=_tasks.pop(user_id,None)
    if old and not old.done():
        old.cancel()
    _tasks[user_id]=asyncio.create_task(expire(bot,user_id,card_id))


async def restore_timeouts(bot):
    p=await pool()
    async with p.acquire() as c:
        rows=await c.fetch("""SELECT user_id,card_message_id,updated_at
            FROM pv_match_sessions WHERE updated_at>now()-interval '3 minutes' LIMIT 500""")
    for r in rows:
        left=180-(datetime.now(timezone.utc)-r["updated_at"]).total_seconds()
        old=_tasks.pop(r["user_id"],None)
        if old:
            old.cancel()
        _tasks[r["user_id"]]=asyncio.create_task(
            expire(bot,r["user_id"],r["card_message_id"],left))


async def shutdown():
    jobs=list(_tasks.values())
    _tasks.clear()
    for job in jobs:
        job.cancel()
    if jobs:
        await asyncio.gather(*jobs,return_exceptions=True)


async def begin(update,context,source_group):
    from handlers import member, match_caption
    uid=update.effective_user.id
    if update.effective_chat.type!="private":
        return
    if not await member(context.bot,source_group,uid):
        await update.effective_message.reply_text("🌷 ဒီ Group ထဲမှာ ရှိမှ လှည့်ကြည့်လို့ရမယ်နော်။")
        return
    options=await db.group_settings(source_group)
    if not options["matchmaking"] or not options["requests"]:
        await update.effective_message.reply_text("🌷 ဒီ Group မှာ လူတောင်းပွဲကို ခဏနားထားတယ်နော်။")
        return
    own=await db.get_profile(uid,source_group)
    if not own or not own["adult_self_confirmed"]:
        await update.effective_message.reply_text("💗 အသက် ၁၈ နှစ်ပြည့်သူတွေအတွက်ပဲ ဖွင့်ထားတာပါ။ Group ထဲက /register နဲ့ အတည်ပြုပေးနော်။")
        return
    if await get_session(uid):
        from responses import say
        await update.effective_message.reply_text(say("match_in_progress",uid),reply_markup=KEYBOARD)
        return
    profiles=await db.browse_profiles(uid,source_group,limit=50)
    if not profiles:
        await update.effective_message.reply_text("🌷 အခုတော့ ကြည့်စရာ Profile မရှိသေးဘူးနော်။")
        return
    # Avoid duplicate cards from earlier completed sessions.
    await finish(uid)
    profile=profiles[0]
    caption=await match_caption(context.bot,profile)
    try:
        kw=dict(caption=caption,parse_mode="HTML",reply_markup=KEYBOARD)
        if profile["media_type"]=="video":
            card=await context.bot.send_video(uid,profile["media_file_id"],**kw)
        else:
            card=await context.bot.send_photo(uid,profile["media_file_id"],**kw)
    except TelegramError:
        logging.exception("PV first profile delivery failed")
        await update.effective_message.reply_text("🌷 Profile ကတ်လေး ဖွင့်မရသေးဘူးနော်။")
        return
    await save_session(uid,source_group,card.message_id,
                       [[p["user_id"],p["group_id"]] for p in profiles])
    await db.mark_profile_viewed(uid,source_group,profile["user_id"],profile["group_id"])
    reset_timeout(context.bot,uid,card.message_id)


async def handle_reply(update,context):
    from handlers import match_caption
    uid=update.effective_user.id
    text=update.message.text
    try:
        await update.message.delete()
    except TelegramError:
        pass
    session=await get_session(uid)
    if not session:
        await update.effective_chat.send_message("🌷 ကြည့်နေတဲ့ကတ်လေး သက်တမ်းကုန်သွားပြီနော်။ Group ထဲက /match နဲ့ ပြန်စပါ။",
                                                 reply_markup=ReplyKeyboardRemove())
        return
    if text==STOP:
        await finish(uid)
        task=_tasks.pop(uid,None)
        if task: task.cancel()
        await retire(context.bot,uid,session["card_message_id"])
        await context.bot.send_message(uid,"💗 ဒီနေ့တော့ ဒီလောက်ပဲနော်။",
                                      reply_markup=ReplyKeyboardRemove())
        return
    keys=session["profile_keys"]
    if isinstance(keys,str): keys=json.loads(keys)
    if text==REQUEST:
        key=profile_key(session)
        if not key:
            return
        target=await db.get_profile(key[0],key[1])
        source=await db.get_profile(uid,session["source_group_id"])
        if not target or not source:
            await context.bot.send_message(uid,"🌷 ဒီ Profile လေး မရှိတော့ဘူးနော်။ ကျော်ကြည့်ပေးပါ။")
            return
        await context.bot.send_message(uid,
            f"💌 <b>{html.escape(source['display_name'])}</b> က <b>{html.escape(target['display_name'])}</b> ဆီ တောင်းမလား?",
            parse_mode="HTML",reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💌 တကယ်တောင်းမယ်",
                  callback_data=f"pvreq:{uid}:{session['source_group_id']}:{key[0]}:{key[1]}")],
                [InlineKeyboardButton("🌷 စိတ်ပြောင်းပြီ",callback_data="pvreq_cancel")]]))
        await set_position(uid,session["card_message_id"],session["position"])
        reset_timeout(context.bot,uid,session["card_message_id"])
        return
    if text!=SKIP:
        return
    next_pos=session["position"]+1
    if next_pos>=len(keys):
        await context.bot.send_message(uid,"🌷 အကုန်ကြည့်ပြီးပြီနော်။ /match နဲ့ နောက်တစ်ခေါက် ပြန်စနိုင်တယ်။",
                                       reply_markup=ReplyKeyboardRemove())
        await finish(uid)
        await retire(context.bot,uid,session["card_message_id"])
        return
    target=await db.get_profile(keys[next_pos][0],keys[next_pos][1])
    if not target:
        await set_position(uid,session["card_message_id"],next_pos)
        await context.bot.send_message(uid,"🌷 ဒီ Profile လေး မရှိတော့ဘူးနော်။ နောက်တစ်ယောက်ကို ကျော်ကြည့်ပါ။")
        return
    caption=await match_caption(context.bot,target)
    deleted=await retire(context.bot,uid,session["card_message_id"])
    if deleted:
        kw=dict(caption=caption,parse_mode="HTML",reply_markup=KEYBOARD)
        if target["media_type"]=="video":
            msg=await context.bot.send_video(uid,target["media_file_id"],**kw)
        else:
            msg=await context.bot.send_photo(uid,target["media_file_id"],**kw)
        await set_position(uid,session["card_message_id"],next_pos,msg.message_id)
        reset_timeout(context.bot,uid,msg.message_id)
    else:
        # Avoid duplicate cards when Telegram deletion is unavailable.
        from telegram import InputMediaPhoto,InputMediaVideo
        media=InputMediaVideo(target["media_file_id"],caption=caption,parse_mode="HTML") if target["media_type"]=="video" else InputMediaPhoto(target["media_file_id"],caption=caption,parse_mode="HTML")
        await context.bot.edit_message_media(media=media,chat_id=uid,message_id=session["card_message_id"])
        await set_position(uid,session["card_message_id"],next_pos)
        reset_timeout(context.bot,uid,session["card_message_id"])
    await db.mark_profile_viewed(uid,session["source_group_id"],target["user_id"],target["group_id"])


async def confirm(update,context):
    from handlers import member,group_label,media_caption,show_profile
    q=update.callback_query
    if q.data=="pvreq_cancel":
        await q.answer()
        await q.edit_message_text("🌷 မပို့တော့ဘူးနော်။")
        return
    try:
        _,user_text,source_text,target_text,target_gid_text=q.data.split(":")
        uid,source_gid,target_id,target_gid=map(int,(user_text,source_text,target_text,target_gid_text))
    except (ValueError,AttributeError):
        await q.answer("ခလုတ်လေး မမှန်တော့ဘူးနော်။",show_alert=True)
        return
    if q.message.chat.type!="private" or q.from_user.id!=uid:
        await q.answer("ဒီခလုတ်လေးက ကိုယ့်အတွက်ပဲနော်။",show_alert=True)
        return
    session=await get_session(uid)
    if not session or session["source_group_id"]!=source_gid or profile_key(session)!=[target_id,target_gid]:
        await q.answer("Profile ကတ်လေး ပြောင်းသွားပြီနော်။",show_alert=True)
        return
    if not (await db.group_settings(source_gid))["requests"]:
        await q.answer("ဒီဝိုင်းမှာ တောင်းခွင့် ခဏပိတ်ထားတယ်နော်။",show_alert=True)
        return
    if not await member(context.bot,source_gid,uid) or not await member(context.bot,target_gid,target_id):
        await q.answer("Group ထဲမှာ မရှိတော့သူ ပါနေတယ်နော်။",show_alert=True)
        return
    sender=await db.get_profile(uid,source_gid)
    recipient=await db.get_profile(target_id,target_gid)
    if not sender or not recipient or not sender["adult_self_confirmed"] or not recipient["adult_self_confirmed"]:
        await q.answer("အတည်ပြုထားတဲ့ Profile လေး မရှိတော့ဘူးနော်။",show_alert=True)
        return
    result=await db.send_request(uid,source_gid,target_id,target_gid)
    if not result:
        await q.answer("တောင်းထားပြီးသား ဒါမှမဟုတ် ခဏစောင့်ရဦးမယ်နော်။",show_alert=True)
        return
    await q.answer("💌 ပို့လိုက်ပြီနော်။")
    await q.edit_message_text("💌 တောင်းစာလေး ပို့လိုက်ပြီနော်။")
    left_label=await group_label(context.bot,source_gid)
    right_label=await group_label(context.bot,target_gid)
    reqid=result["id"]
    # Source group: recipient's image; only sender's own account is linked.
    a_quotes=request_quotes(sender,recipient,reqid,left_label,right_label,
                            sender_id=uid,recipient_id=target_id,sender_side=True)
    # Recipient group: sender's image; sender account hidden until acceptance.
    b_quotes=request_quotes(sender,recipient,reqid,left_label,right_label,
                            sender_id=uid,recipient_id=target_id,sender_side=False)
    errors=[]
    try:
        a=await show_profile(context.bot,source_gid,recipient,None,header=a_quotes)
        p=await pool()
        async with p.acquire() as c:
            await c.execute("""UPDATE requests SET sender_card_message_id=$2 WHERE id=$1""",reqid,a.message_id)
    except TelegramError:
        logging.exception("Sender group request card failed")
        errors.append("တောင်းသူ Group")
    try:
        b=await show_profile(context.bot,target_gid,sender,
            InlineKeyboardMarkup([[InlineKeyboardButton("💌 အဖြေပေးမယ်",
            callback_data=f"reply:{reqid}:{target_id}")]]),header=b_quotes)
        await db.remember_request_group_message(reqid,target_id,"card",b.message_id)
    except TelegramError:
        logging.exception("Recipient group request card failed")
        errors.append("လက်ခံသူ Group")
    if errors:
        await context.bot.send_message(uid,"🌷 Request ကို သိမ်းထားပေမဲ့ " + "၊ ".join(errors)+" မှာ Card မပေါ်နိုင်ခဲ့ဘူး။")
    # Keep the current preview so another target can be reached via Skip.
    await set_position(uid,session["card_message_id"],session["position"])
    reset_timeout(context.bot,uid,session["card_message_id"])
