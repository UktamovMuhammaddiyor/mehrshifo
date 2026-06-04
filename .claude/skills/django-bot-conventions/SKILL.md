---
name: django-bot-conventions
description: >-
  Use when changing this Django Telegram bot's backend — adding a command or
  callback, editing models, running migrations, or understanding the getPost
  dispatch and the BotUser.status state machine. Covers the project's
  structure, conventions, and the commands to run.
---

# Django bot conventions (this repo)

A Django 5.0.1 Telegram bot. Django is the HTTP/ORM/admin layer; all bot logic lives in the single app `pages`. User-facing text is in **Uzbek**.

## Layout & commands

The Django project is in `main/`. Run everything from there:

```bash
cd main
python manage.py runserver
python manage.py makemigrations      # after editing pages/models.py
python manage.py migrate
python manage.py createsuperuser     # for /admin/
python manage.py test                # runner; run a single test:
python manage.py test pages.tests.ClassName.test_method
```

`requirements.txt` is **UTF-16 LE** — `pip install -r` may fail to parse it; re-encode to UTF-8 first or install packages by hand. `settings.py` ships `DEBUG=True` with a committed `SECRET_KEY` (dev config).

Routes (`pages/urls.py`): `/` (health string), `/setwebhook/` (register webhook), `/getpost/` (the bot — CSRF-exempt).

## Pattern 1 — the `getPost` dispatcher

`getPost` in `pages/views.py` handles every update. It branches on the top-level update key:

- `message` → then on `chat['type']` (private vs. group/supergroup/channel)
- `callback_query` → inline-button presses, branched on `data`
- `my_chat_member` → auto-registers `ChannelBot` / `GroupBot` when the bot becomes admin

**Adding a feature = a new branch in `getPost` + (for outbound calls) a wrapper in `TelegramAPI.py`.** Mind the `elif` order — an earlier branch can shadow a later one.

## Pattern 2 — conversational FSM via `BotUser.status`

Multi-step admin flows use the `status` text field on `BotUser` as state:

1. A command (e.g. `/addchannel`) sets `user.status = 'addingChannel'` and prompts.
2. The user's **next** message hits `elif user.status == 'addingChannel':`, which does the work and resets `status = ''`.

Existing statuses: `getAdmin`, `addingChannel`, `creatingmainpost`, `addingAnswer`, `addingPost`, `addingChannelPost`, `addingPostAnswer`, `addinganswer`. **New multi-step flows must follow this exact contract — do not introduce a separate state store.** Always `user.save()` after mutating.

## Pattern 3 — single-row config models

`AboutMessage`, `ChannelMessage`, and `AutoAnswer` are treated as one live config row: code reads `.objects.all()[0]` / `.first()` and frequently **deletes existing rows before creating a new one**. Don't assume multiple rows exist; handle the empty table (this is where `IndexError`s hide).

## Models (`pages/models.py`)

- `BotUser` — Telegram users; `is_admin`, `is_subcribe`, FSM `status`, `user_id`.
- `AboutMessage` — forced-subscription config + broadcast "main post"; `is_active` toggles mandatory subscription.
- `ChannelMessage` — channel post with hidden `answer` revealed via inline button, gated by membership.
- `ChannelBot` / `GroupBot` — channels/groups the bot administers; `GroupBot` is the support-forwarding target, activated by password.
- `AutoAnswer` — single auto-reply text.

Register new models in `pages/admin.py`. After any model change, generate + commit a migration — the 17 migrations in `pages/migrations/` are the schema's source of truth.

## Auth

Admin promotion (`/getadmin`) and group activation are gated by a hardcoded password literal in `views.py` (`WTlJgvNGS3PZGOv`). If improving auth, flag the change explicitly rather than silently altering the model.

For Telegram-specific calls and payload shapes, see the **telegram-bot-api** skill.
