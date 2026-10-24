import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from handlers import handlers, restore_browse_timeouts, shutdown_browse_timeouts
from db import init_schema, close as close_db

logging.basicConfig(level=logging.INFO)
# HTTP client request logs may include Telegram bot credentials in URL paths.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
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
        for handler in handlers():
            telegram_app.add_handler(handler)
        if os.getenv("DATABASE_URL"):
            await init_schema()
        else:
            logging.warning("DATABASE_URL missing: registration and matching unavailable")
        await telegram_app.initialize()
        await telegram_app.start()
        if os.getenv("DATABASE_URL"):
            await restore_browse_timeouts(telegram_app.bot)
        if BASE_URL and SECRET:
            await telegram_app.bot.set_webhook(BASE_URL + "/telegram/webhook", secret_token=SECRET)
        else:
            logging.warning("PUBLIC_BASE_URL or WEBHOOK_SECRET missing; webhook not registered")
    else:
        logging.warning("BOT_TOKEN missing; health endpoint only")
    yield
    if telegram_app:
        await shutdown_browse_timeouts()
        await telegram_app.stop()
        await telegram_app.shutdown()
    await close_db()

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok", "bot_configured": bool(TOKEN), "webhook_configured": bool(TOKEN and SECRET and BASE_URL), "database_configured": bool(os.getenv("DATABASE_URL"))}

@app.post("/telegram/webhook")
async def webhook(request: Request):
    if not telegram_app or not SECRET or request.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Update must be an object")
        update = Update.de_json(payload, telegram_app.bot)
        if update is None:
            raise ValueError("Empty update")
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Telegram update") from exc
    await telegram_app.process_update(update)
    return {"ok": True}
