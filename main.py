import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN", "")
SECRET = os.getenv("WEBHOOK_SECRET", "")
BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
telegram_app = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("💘 လူတောင်းပွဲက ကြိုဆိုပါတယ်။ Bot ကို ပြင်ဆင်နေဆဲပါနော်။")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app
    if TOKEN:
        telegram_app = Application.builder().token(TOKEN).build()
        telegram_app.add_handler(CommandHandler("start", start))
        await telegram_app.initialize()
        await telegram_app.start()
        if BASE_URL and SECRET:
            await telegram_app.bot.set_webhook(BASE_URL + "/telegram/webhook", secret_token=SECRET)
    else:
        logging.warning("BOT_TOKEN missing; health endpoint only")
    yield
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok", "bot_configured": bool(TOKEN)}

@app.post("/telegram/webhook")
async def webhook(request: Request):
    if not telegram_app or not SECRET or request.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    payload = await request.json()
    update = Update.de_json(payload, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}
