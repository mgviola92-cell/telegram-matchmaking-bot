"""Reply-keyboard navigation for private incoming/outgoing requests.

Only request IDs fetched from the user's own DB query are accepted. Each
action is revalidated against the current DB state, never from button text.
"""
import logging
import re
from types import SimpleNamespace
from telegram import ReplyKeyboardMarkup
from telegram.error import TelegramError
import repository as db
import pv_matching

BACK="⬅️ နောက်ပြန်"
ACCEPT="💕 လက်ခံမယ်"
REJECT="💔 ငြင်းမယ်"
WITHDRAW="📮 ပြန်ရုပ်သိမ်းမယ်"
CONFIRM="✅ သေချာပြန်ရုပ်သိမ်းမယ်"
CANCEL="🌷 မလုပ်တော့ဘူး"
NOTE_WRITE="💬 အကြောင်းပြချက်ရေးမယ်"
NOTE_SKIP="🌷 မရေးတော့ဘူး"
NOTE_CONFIRM="💌 စကားလေး ပို့မယ်"
NOTE_CANCEL="🌷 စကားမပို့တော့ဘူး"

def keyboard(rows):
    return ReplyKeyboardMarkup(rows,resize_keyboard=True,is_persistent=True)

def options(state):
    state["choices"]={}
    rows=[]
    for item in state["rows"][:25]:
        text=f"💌 #{item['id']} {item['nickname'][:26]}" if state["kind"]=="inbox" else f"📮 #{item['id']} {item['nickname'][:26]}"
        state["choices"][text]=item["id"]
        rows.append([text])
    rows.append([BACK])
    return keyboard(rows)

async def open_menu(update,context,kind):
    uid=update.effective_user.id
    if update.effective_chat.type!="private":
        return
    if kind=="inbox":
        items=await db.incoming_requests(uid)
        other_field="sender_id"
        group_field="sender_group_id"
    else:
        items=await db.outgoing_requests(uid)
        other_field="recipient_id"
        group_field="recipient_group_id"
    rows=[]
    for item in items[:25]:
        profile=await db.get_profile(item[other_field],item[group_field])
        rows.append({"id":item["id"],"nickname":profile["display_name"] if profile else "မိတ်ဆွေ"})
    if not rows:
        await update.effective_message.reply_text(
            "🌷 အခု စာလေးတွေ မရှိသေးဘူးနော်။",reply_markup=pv_matching.MAIN_KEYBOARD)
        return
    state={"kind":kind,"mode":"list","rows":rows}
    context.user_data["pv_requests"]=state
    await update.effective_message.reply_text(
        "💌 ဖွင့်ကြည့်ချင်တဲ့ စာလေးကို ရွေးပေးနော်။" if kind=="inbox" else
        "📮 ပို့ထားတဲ့စာတွေထဲက ရွေးပေးနော်။",reply_markup=options(state))

async def open_incoming_direct(update,context,request_id):
    """Enter a group-origin request in private using ReplyKeyboard."""
    uid=update.effective_user.id
    req=await db.pending_request_for_recipient(request_id,uid)
    if not req:
        await update.effective_message.reply_text(
            "🌷 ဒီဖိတ်ခေါ်စာလေးကို ဖွင့်လို့မရတော့ဘူးနော်။",
            reply_markup=pv_matching.MAIN_KEYBOARD)
        return False
    state={"kind":"inbox","mode":"list","rows":[],"choices":{}}
    context.user_data["pv_requests"]=state
    shown=await show_item(update,context,state,request_id)
    if not shown:
        context.user_data.pop("pv_requests",None)
    return bool(shown)


async def show_item(update,context,state,rid):
    uid=update.effective_user.id
    from handlers import show_profile,request_header
    if state["kind"]=="inbox":
        req=await db.pending_request_for_recipient(rid,uid)
        other=await db.get_profile(req["sender_id"],req["sender_group_id"]) if req else None
        if not req or not other:
            await update.effective_message.reply_text("🌷 ဒီစာလေး မရှိတော့ဘူးနော်။")
            return
        target=await db.get_profile(uid,req["recipient_group_id"])
        header=await request_header(context.bot,other,target or
            {"display_name":"မိတ်ဆွေ"},rid,req["sender_group_id"],req["recipient_group_id"])
        await show_profile(context.bot,uid,other,None,header=header)
        keys=[[ACCEPT,REJECT],[BACK]]
    else:
        rows=await db.outgoing_requests(uid)
        req=next((r for r in rows if r["id"]==rid),None)
        other=await db.get_profile(req["recipient_id"],req["recipient_group_id"]) if req else None
        if not req or not other:
            await update.effective_message.reply_text("🌷 ဒီစာလေး မရှိတော့ဘူးနော်။")
            return
        from handlers import match_caption
        await show_profile(context.bot,uid,other,None,
                           full_caption=await match_caption(context.bot,other))
        keys=[[WITHDRAW],[BACK]]
    state["mode"]="item"
    state["request_id"]=rid
    await update.effective_message.reply_text(
        "💗 အောက်က ခလုတ်လေးတွေကနေ ဆက်ရွေးနိုင်တယ်နော်။",reply_markup=keyboard(keys))
    return True


async def _answer(update,context,rid,action):
    """Reuse the existing recipient-only resolution and notifications."""
    from handlers import decide_callback
    async def answer(*args,**kwargs):
        return None
    async def edit_reply_markup(*args,**kwargs):
        return None
    async def msg_reply(text,**kwargs):
        if action=="rejected":
            context.user_data["pv_rejection_note"]={"rid":rid,"mode":"choose"}
            text+="\n💬 အကြောင်းပြချက် မရေးချင်လည်း ရပါတယ်နော်။"
            reply=keyboard([[NOTE_WRITE,NOTE_SKIP]])
        else:
            reply=pv_matching.MAIN_KEYBOARD
        return await update.effective_message.reply_text(text,reply_markup=reply)
    proxy_msg=SimpleNamespace(chat=update.effective_chat,reply_text=msg_reply)
    q=SimpleNamespace(data=f"decide:{rid}:{action}",from_user=update.effective_user,
        message=proxy_msg,answer=answer,edit_message_reply_markup=edit_reply_markup)
    await decide_callback(SimpleNamespace(callback_query=q),context)


async def _withdraw(update,context,rid):
    from handlers import withdraw_do
    async def answer(*args,**kwargs):
        return None
    async def edit_text(text,**kwargs):
        return await update.effective_message.reply_text(
            text,reply_markup=pv_matching.MAIN_KEYBOARD)
    q=SimpleNamespace(data=f"withdraw_do:{rid}",from_user=update.effective_user,
        message=SimpleNamespace(chat=update.effective_chat),answer=answer,
        edit_message_text=edit_text)
    await withdraw_do(SimpleNamespace(callback_query=q),context)


async def handle(update,context):
    if update.effective_chat.type!="private":
        return False
    state=context.user_data.get("pv_requests")
    if not state:
        return False
    text=update.effective_message.text
    if text==BACK:
        if state["mode"]=="list":
            context.user_data.pop("pv_requests",None)
            await update.effective_message.reply_text(
                "💗 ပင်မ Menu ကို ပြန်ရောက်ပြီနော်။",
                reply_markup=pv_matching.MAIN_KEYBOARD)
        else:
            state["mode"]="list"
            await update.effective_message.reply_text(
                "💌 စာလေးတွေ ပြန်ရွေးနိုင်ပြီနော်။",reply_markup=options(state))
        return True
    if state["mode"]=="list":
        rid=state["choices"].get(text)
        if rid is None:
            return False
        await show_item(update,context,state,rid)
        return True
    if state["mode"]=="item":
        if text==WITHDRAW and state["kind"]=="outgoing":
            state["mode"]="withdraw"
            await update.effective_message.reply_text(
                "📮 ဒီဖိတ်ခေါ်စာကို တကယ်ပြန်ရုပ်သိမ်းမလား?",
                reply_markup=keyboard([[CONFIRM,CANCEL],[BACK]]))
            return True
        if text in (ACCEPT,REJECT) and state["kind"]=="inbox":
            rid=state["request_id"]
            context.user_data.pop("pv_requests",None)
            await _answer(update,context,rid,"accepted" if text==ACCEPT else "rejected")
            if "pv_rejection_note" not in context.user_data:
                await update.effective_message.reply_text(
                    "💗 အဖြေပေးပြီးပြီနော်။",reply_markup=pv_matching.MAIN_KEYBOARD)
            return True
    if state["mode"]=="withdraw":
        if text==CANCEL:
            state["mode"]="item"
            await update.effective_message.reply_text(
                "🌷 ဆက်စောင့်ကြည့်နိုင်တယ်နော်။",reply_markup=keyboard([[WITHDRAW],[BACK]]))
            return True
        if text==CONFIRM:
            rid=state["request_id"]
            context.user_data.pop("pv_requests",None)
            await _withdraw(update,context,rid)
            return True
    return False

async def handle_rejection_note(update,context):
    """Optional free-text reason, private and explicitly approved by recipient."""
    if update.effective_chat.type!="private":
        return False
    state=context.user_data.get("pv_rejection_note")
    if not state:
        return False
    text=update.effective_message.text
    mode=state["mode"]
    if text in (NOTE_SKIP,NOTE_CANCEL):
        context.user_data.pop("pv_rejection_note",None)
        await update.effective_message.reply_text(
            "🌷 စကားလေးကို မမျှဝေတော့ဘူးနော်။",reply_markup=pv_matching.MAIN_KEYBOARD)
        return True
    if mode=="choose" and text==NOTE_WRITE:
        state["mode"]="draft"
        await update.effective_message.reply_text(
            "💬 စကားလေးကို စာလုံး ၂၀၀ အတွင်း ရေးပေးနော်။",
            reply_markup=keyboard([[NOTE_CANCEL]]))
        return True
    if mode=="draft":
        if not (1<=len(text.strip())<=200):
            await update.effective_message.reply_text(
                "🌷 စာလုံး ၁–၂၀၀ အတွင်း ရေးပေးနော်။")
            return True
        state["text"]=text.strip()
        state["mode"]="confirm"
        await update.effective_message.reply_text(
            "💌 ဒီစကားလေးကို တစ်ဖက်သူဆီ တကယ်ပို့မလား?\n\n"+state["text"],
            reply_markup=keyboard([[NOTE_CONFIRM,NOTE_CANCEL]]))
        return True
    if mode=="confirm" and text==NOTE_CONFIRM:
        rid=state["rid"]
        text_to_share=state["text"]
        context.user_data.pop("pv_rejection_note",None)
        saved=await db.save_rejection_reason(
            rid,update.effective_user.id,text_to_share)
        if saved:
            try:
                await context.bot.send_message(saved["sender_id"],
                    "🌷 ဖိတ်ခေါ်စာအတွက် လက်ခံသူက မျှဝေဖို့ သဘောတူထားတဲ့ စကားလေးပါ။\n\n"
                    +text_to_share)
            except TelegramError:
                logging.info("Could not deliver optional rejection note")
        await update.effective_message.reply_text(
            "💌 စကားလေး ပို့ပြီးပြီနော်။" if saved else
            "🌷 စကားလေး မပို့နိုင်တော့ဘူးနော်။",
            reply_markup=pv_matching.MAIN_KEYBOARD)
        return True
    return False
