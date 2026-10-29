"""Telegram-side cleanup for a deleted global profile.

Database removal is atomic in repository.delete_profile. Telegram deletes are
best-effort: the bot cannot bypass its message deletion/permission limits.
"""
import logging
from telegram.error import TelegramError
import pv_matching

REVOKED="🌷 ဒီမိတ်ဆက်ကတ်လေးကို ဖယ်ရှားထားပြီးပါပြီ။"

async def remove_card(bot,chat_id,message_id):
    if not message_id:
        return True
    try:
        await bot.delete_message(chat_id=chat_id,message_id=message_id)
        return True
    except TelegramError:
        # Revoke actions and redact text where deletion is no longer allowed.
        try:
            await bot.edit_message_caption(
                chat_id=chat_id,message_id=message_id,
                caption=REVOKED,reply_markup=None)
            return False
        except TelegramError:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,message_id=message_id,
                    text=REVOKED,reply_markup=None)
            except TelegramError:
                try:
                    await bot.edit_message_reply_markup(
                        chat_id=chat_id,message_id=message_id,reply_markup=None)
                except TelegramError:
                    logging.warning("Cannot revoke deleted-profile message %s/%s",
                                    chat_id,message_id)
    return False


async def cleanup_deleted_profile(bot,owner_id,result,*,own_card_id=None):
    """Revoke all recorded references and notify only pending request peers."""
    if not result:
        return
    deleted=set()
    async def once(chat_id,message_id):
        if message_id is None:
            return
        item=(int(chat_id),int(message_id))
        if item in deleted:
            return
        deleted.add(item)
        await remove_card(bot,*item)

    for r in result.get("affected_requests",result.get("affected",[])):
        await once(r.get("sender_group_id"),r.get("sender_card_message_id"))
        await once(r.get("recipient_group_id"),r.get("group_card_message_id"))
        await once(r.get("recipient_group_id"),r.get("group_prompt_message_id"))
    for r in result.get("intro_cards",[]):
        await once(r["group_id"],r["message_id"])
    for r in result.get("old_cards",[]):
        key=(r["viewer_id"],r["group_id"])
        job=__import__("handlers")._browse_timer_tasks.pop(key,None)
        if job and not job.done():
            job.cancel()
        await once(r["group_id"],r.get("message_id"))
    pv_viewers=set()
    for r in result.get("pv_cards",[]):
        uid=r["user_id"]
        job=pv_matching._tasks.pop(uid,None)
        if job and not job.done():
            job.cancel()
        await once(uid,r.get("card_message_id"))
        if uid!=owner_id:
            pv_viewers.add(uid)
    await once(owner_id,own_card_id)
    recipients=set(pv_viewers)
    for r in result.get("affected",[]):
        recipients.update((r["sender_id"],r["recipient_id"]))
    recipients.discard(owner_id)
    for uid in recipients:
        try:
            await bot.send_message(
                uid,"🌷 ဆိုင်ရာ Profile ကို ဖယ်ရှားလိုက်လို့ ကတ်/ဖိတ်ခေါ်စာဟောင်း မရနိုင်တော့ဘူးနော်။",
                reply_markup=pv_matching.MAIN_KEYBOARD if uid in pv_viewers else None)
        except TelegramError:
            logging.info("Could not notify viewer %s about removed profile",uid)
