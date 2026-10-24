"""Trusted owner identifier. Set this once in GitHub (not in the Render dashboard).

Do not automatically claim ownership for the first Telegram user who sends /owner:
anyone could seize a fresh bot. Telegram numeric user IDs are not credentials.
"""
OWNER_TELEGRAM_ID = 0
