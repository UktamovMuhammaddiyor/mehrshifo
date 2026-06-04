# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Telegram bot built on Django 5.0.1. There is no user-facing website — the single HTTP endpoint that matters is a Telegram webhook. Django serves as the HTTP layer, ORM, and admin UI; all bot behavior lives in one app, `pages`. Bot-facing text is written in Uzbek.

## Project layout

The git repo root is this directory. The Django project lives one level down in `main/`:

- `main/manage.py` — run all Django commands from inside `main/`.
- `main/main/` — project config (`settings.py`, `urls.py`, `wsgi.py`, `asgi.py`).
- `main/pages/` — the only app; contains all bot logic.
- `main/db.sqlite3` — SQLite database (gitignored; not committed).

## Commands

All commands run from `main/`:

```bash
python manage.py runserver        # start dev server
python manage.py migrate          # apply migrations
python manage.py makemigrations   # after editing pages/models.py
python manage.py createsuperuser  # for /admin/
python manage.py test             # test runner (pages/tests.py is an empty stub)
python manage.py test pages.tests.ClassName.test_method  # single test
```

`requirements.txt` is UTF-8 encoded. Install with `pip install -r requirements.txt` as usual.

## Local setup the code requires

1. **`pages/creditionals.py` is committed empty** but `views.py` and `TelegramAPI.py` import `BOT_URL` and `URL` from it. It must define:
   - `BOT_URL` — Telegram Bot API base ending in a slash, e.g. `https://api.telegram.org/bot<token>/`
   - `URL` — the public HTTPS URL Telegram will POST updates to (the `/getpost/` endpoint).
   The filename keeps its original spelling (`creditionals`, not `credentials`).
2. Telegram requires a public HTTPS webhook. Dev uses an **ngrok tunnel** — `ALLOWED_HOSTS` in `settings.py` lists an ngrok host; update it to your current tunnel.
3. Register the webhook by hitting **`GET /setwebhook/`** once (the `setWebHook` view calls Telegram's `setWebhook` with `URL`).

`settings.py` ships with `DEBUG = True` and a committed `SECRET_KEY` — development config, not production-ready.

## Routing

`main/urls.py` mounts `admin/` and includes `pages.urls`, which exposes three routes:
- `/` → `index` (returns a plain "Hello World" health string).
- `/setwebhook/` → registers the Telegram webhook.
- `/getpost/` → **the bot**. CSRF-exempt; this is where every Telegram update arrives.

## How the bot works (the important part)

Everything funnels through `getPost` in `pages/views.py` — one large function that parses the incoming Telegram update JSON and branches on the update type:

- **`message`** — a user or group message. Further branches on `chat['type']` (private vs. group/supergroup/channel).
- **`callback_query`** — an inline-button press (subscription toggles, "reveal answer", subscription check).
- **`my_chat_member`** — the bot's membership changed; used to auto-register channels (`ChannelBot`) and groups (`GroupBot`) when the bot is added as admin.

**The conversational state machine is `BotUser.status`** — a free-text field on the user row that drives multi-step admin flows. A command like `/addchannel` sets `status = 'addingChannel'`; the *next* message from that user is interpreted according to that status, then `status` is cleared. When editing admin flows, the contract is: command handler sets a status string and prompts; a matching `elif user.status == '...'` branch consumes the next message. Known statuses: `getAdmin`, `addingChannel`, `creatingmainpost`, `addingAnswer`, `addingPost`, `addingChannelPost`, `addingPostAnswer`, `addinganswer`.

Admin access and group activation are gated by a **hardcoded password literal** (`WTlJgvNGS3PZGOv`) checked inline in `views.py`. `/getadmin` + password promotes a `BotUser` to admin and reveals the admin reply-keyboard.

### Telegram API layer

`pages/TelegramAPI.py` holds thin `requests.post` wrappers over Bot API methods (`sentMessage`, `answerCallbackQuery`, `getMemberInformation`, `forwardMessage`, `deleteMessage`). Add new Telegram calls here rather than inlining `requests` in views. Note `sentMessage` accepts a custom list shorthand for `reply_markup` (`['inline_keyboard', [[[text, callback_data, url], ...]]]`) which it expands into the Telegram keyboard JSON.

### Data model (`pages/models.py`)

Single-row "config" tables are the norm — code frequently does `.objects.all()[0]` or `.first()` and treats it as the one live config object, deleting existing rows before creating a new one:
- `BotUser` — Telegram users; carries `is_admin`, `is_subcribe`, and the FSM `status`.
- `AboutMessage` — the forced-subscription config + the broadcast "main post" (channel link, `chat_id`, `is_active` toggles mandatory subscription).
- `ChannelMessage` — a channel post with a hidden `answer` revealed via inline button, gated by channel membership.
- `ChannelBot` / `GroupBot` — channels and groups the bot administers; `GroupBot` is where non-admin users' messages get forwarded (support routing) once activated by password.
- `AutoAnswer` — single auto-reply text sent to users who message the bot.

### Core behaviors implemented in the dispatch

Forced channel subscription (membership checked via `userHasMemberOfChannel` → `getChatMember`), broadcasting a post to all `BotUser`s, forwarding ordinary users' messages into the support `GroupBot`, and quiz-style channel posts whose answer is gated behind subscription.

## Editing notes

- After changing `pages/models.py`, generate and commit a migration — the existing 17 migrations in `pages/migrations/` are the source of truth for the SQLite schema.
- New bot interactions are almost always a new branch inside `getPost` plus (for outbound calls) a helper in `TelegramAPI.py`. Match the existing status-string FSM pattern rather than introducing a separate state store.

## AI customer support (pages/ai, pages/knowledge, pages/handlers)

Customer private messages are no longer forwarded inline. `getPost` verifies the
`X-Telegram-Bot-Api-Secret-Token` header, dedupes by `update_id` (`ProcessedUpdate`),
and enqueues `pages.tasks.process_client_message` on the Django-Q2 queue. The worker runs
`pages/ai/pipeline.py` (gates → grounded OpenAI call → routing) and `pages/handlers/private_ai.py`
sends the reply to the customer + mirrors it into the support group. Staff replies in the
group are handled by `pages/handlers/group.py` (relay via `copyMessage` + set conversation
to `handoff`; `/ai_resume` reactivates).

KB lives in `Service/Doctor/ClinicInfo/FAQ` (edit in Django admin); `pages/knowledge/snapshot.py`
caches the assembled KB text and invalidates it on save, so price edits apply immediately.
The LLM only returns text + intent; all side effects are in our code. Toggle with `/ai_on`
`/ai_off` (allowlisted via `ADMIN_USER_IDS`); inspect with `/ai_status`.

### Running it
- `python manage.py createcachetable` once (DatabaseCache, shared across processes).
- Run the worker alongside the web process: `python manage.py qcluster`.
- New env vars: `OPENAI_API_KEY`, `TELEGRAM_WEBHOOK_SECRET`, `ADMIN_USER_IDS` (see `.env.example`).
- Re-register the webhook (`GET /setwebhook/`) after setting `TELEGRAM_WEBHOOK_SECRET`.
- Tests use in-memory cache automatically; run `python manage.py test pages`.
