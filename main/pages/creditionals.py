"""Per-environment bot secrets and config, sourced from the .env file.

settings.py calls load_dotenv() before this module is imported (the URLconf, and
therefore views.py, loads after Django settings), so os.environ is already
populated by the time anything reads these values. Tests mock the Telegram
boundary, so the empty defaults below never reach a real network call.
"""
import os

BOT_TOKEN = os.environ.get('BOT_TOKEN', '')

# Telegram Bot API base, e.g. https://api.telegram.org/bot<token>/
BOT_URL = f'https://api.telegram.org/bot{BOT_TOKEN}/'

# Public HTTPS URL Telegram posts updates to (the /getpost/ endpoint).
URL = os.environ.get('WEBHOOK_URL', '')

# Password gating /getadmin and group activation. Defaults to the original
# literal so prod keeps working until a per-environment password is set in .env.
BOT_ADMIN_PASSWORD = os.environ.get('BOT_ADMIN_PASSWORD', 'WTlJgvNGS3PZGOv')
