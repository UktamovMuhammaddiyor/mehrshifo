# Deployment & Operations

How to deploy and run the bot with the AI Customer Support and Mini-App Publishing
subsystems. Consolidated from the three implementation plans' runbooks. Run every command
from `main/` with the virtualenv active.

> **Most important fact:** customer private messages are processed **asynchronously** by the
> Django-Q worker. **The `qcluster` worker MUST be running** or the bot will not reply to or
> forward customer messages at all — they just queue. This is true even when the AI is OFF.

---

## 1. What runs (two processes)

| Process | Command | Role |
|---|---|---|
| Web | your WSGI server (gunicorn/uwsgi); `runserver` in dev | Telegram webhook (`/getpost/`), Django admin (`/admin/`), Mini App (`/miniapp/`) |
| Worker | `python manage.py qcluster` | Processes AI replies + content generation off the queue. **Required.** |

Both must run continuously (use systemd/supervisor in prod).

---

## 2. Prerequisites

- Python 3.13, a virtualenv at `main/.venv`.
- A public **HTTPS** endpoint (Telegram requires HTTPS for both the webhook and the Mini App).
  Dev uses an ngrok tunnel; prod uses your domain.
- A Telegram bot (from @BotFather).
- For publishing: a WordPress site with the REST API enabled, and (optionally) a Telegram channel.

```bash
cd main && source .venv/bin/activate
pip install -r requirements.txt        # UTF-8; includes openai + django-q2
```

---

## 3. Environment variables (`main/.env`)

Copy `main/.env.example` → `main/.env` and fill in. `.env` is git-ignored — never commit secrets.

| Var | Used by | Notes |
|---|---|---|
| `APP_ENV` | DB selection | `prod` → `db.sqlite3` (live); anything else → `db.dev.sqlite3` |
| `DEBUG` | Django | **`False` in prod** |
| `SECRET_KEY` | Django | Real key in prod; rotating it logs admins out |
| `ALLOWED_HOSTS` | Django | Must include your webhook/Mini-App host (no ngrok in prod) |
| `BOT_TOKEN` | bot | From @BotFather. `BOT_URL` is derived from it |
| `WEBHOOK_URL` | webhook | Public HTTPS URL ending in `/getpost/` |
| `BOT_ADMIN_PASSWORD` | admin/group | `/getadmin` + group activation password; use a different value per env |
| `OPENAI_API_KEY` | support + generation | OpenAI key (chat + web search) |
| `TELEGRAM_WEBHOOK_SECRET` | webhook | Shared secret; set it, then re-register the webhook (§5) |
| `ADMIN_USER_IDS` | admin AI cmds + **publishing** | Comma-separated Telegram user IDs. **Publishing is fail-closed: empty = nobody can publish** |
| `WORDPRESS_URL` | publishing | Base site URL, e.g. `https://clinic.example` |
| `WORDPRESS_USER` | publishing | WP username |
| `WORDPRESS_APP_PASSWORD` | publishing | WP **Application Password** (WP admin → Users → Profile → Application Passwords) |
| `MINIAPP_URL` | publishing | Public HTTPS URL ending in `/miniapp/` |

To find your Telegram user ID for `ADMIN_USER_IDS`: message @userinfobot, or check the
`BotUser` table in Django admin after you `/start` the bot.

---

## 4. One-time setup

```bash
python manage.py migrate
python manage.py createcachetable      # DatabaseCache (KB snapshot + rate-limit/cap; shared web↔worker)
python manage.py createsuperuser       # for /admin/
```

---

## 5. Register the Telegram webhook

With `WEBHOOK_URL` and `TELEGRAM_WEBHOOK_SECRET` set and the web process reachable over HTTPS:

```
GET https://<your-host>/setwebhook/        # registers the webhook WITH the secret_token
```

After this, the webhook rejects any request whose `X-Telegram-Bot-Api-Secret-Token` header
doesn't match — so re-run this whenever you change `TELEGRAM_WEBHOOK_SECRET`.

---

## 6. Activate AI Customer Support

1. **Support group:** add the bot to your support group **as an admin**. It auto-registers a
   `GroupBot` and asks for the password; **reply to that prompt in the group with
   `BOT_ADMIN_PASSWORD`** to activate routing.
2. **Become an admin:** DM the bot `/getadmin` then the password (and/or put your Telegram id in
   `ADMIN_USER_IDS`).
3. **Seed the knowledge base** in Django admin (`/admin/`): `ClinicInfo` (one row: name, address,
   hours, days off, phones), `Service` (name + price + duration), `Doctor`, `FAQ`. The AI answers
   **only** from this — incomplete KB ⇒ more escalations. Price edits apply on the next message.
4. **Tune `AISettings`** in admin if needed: model, `confidence_threshold`, `holding_message`,
   `complaint_notify_user_id` (a staff member to DM on complaints), daily cap, etc.
5. **Turn it on:** DM `/ai_on`. Check with `/ai_status`. Turn off anytime with `/ai_off`
   (the bot then falls back to forward-to-group, the legacy behavior).

The worker (§1) must be running for any of this to work.

---

## 7. Activate Mini-App Publishing

1. Set `WORDPRESS_URL` / `WORDPRESS_USER` / `WORDPRESS_APP_PASSWORD` and `MINIAPP_URL` (HTTPS,
   ending `/miniapp/`).
2. Put the staff who may publish into `ADMIN_USER_IDS` (**fail-closed** — without this nobody can
   publish).
3. Re-grant admin (`/getadmin`): the **"✍️ Kontent"** button appears on the admin keyboard when
   `MINIAPP_URL` is set. Tapping it opens the Mini App.
4. In the Mini App: choose post/article, AI or manual, fill the form, (AI) generate → edit the
   draft, pick targets (site / channel / bot users), **Publish**.

WordPress Application Password: in WP admin → Users → your profile → **Application Passwords** →
add one; use it as `WORDPRESS_APP_PASSWORD` with your WP username as `WORDPRESS_USER`.

---

## 8. Production hardening

- `DEBUG=False`, a real `SECRET_KEY`, `ALLOWED_HOSTS` = your real domain (no ngrok).
- HTTPS everywhere (webhook + Mini App).
- `TELEGRAM_WEBHOOK_SECRET` set and the webhook re-registered (§5).
- `ADMIN_USER_IDS` set (gates admin AI commands and, fail-closed, all publishing).
- **`main/db.sqlite3` is git-ignored** (it holds customer conversations — sensitive). Back it up;
  never commit it. Secrets live only in `.env`.
- Run a scheduled retention prune (§9).

---

## 9. Operations

- **Conversation retention (privacy):** schedule daily —
  `python manage.py prune_conversations --days 90` (cron or a Django-Q schedule).
- **Learning loop:** review `FAQSuggestion` rows in Django admin; the **"Approve → create FAQ"**
  action turns a staff answer into a live FAQ. Nothing reaches the KB without approval.
- **Seed FAQs from history (one-off):** export the support group from Telegram Desktop (JSON), then
  `python manage.py import_group_history <export.json>` → creates pending suggestions to review.
- **Monitoring:** `AIDecisionLog` in admin shows every AI decision (intent, confidence, action);
  `/ai_status` shows on/off + today's call count + active handoffs.
- **Kill switch:** `/ai_off` instantly reverts support to forward-only.
- **Handoff:** a staff reply in the group pauses the AI for that customer; reply `/ai_resume` (to the
  forwarded message) to hand back.

---

## 10. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Bot doesn't reply to or forward customer messages | **`qcluster` worker not running** (messages queue). Start it. |
| Webhook returns 403 | `TELEGRAM_WEBHOOK_SECRET` mismatch — re-run `/setwebhook/` after setting it |
| `OperationalError: no such table: mehrshifo_cache` | `createcachetable` not run |
| AI says "savolingiz mutaxassisga yuborildi" for everything | KB empty / `confidence_threshold` too high / `OPENAI_API_KEY` invalid (LLM errors escalate by design — check `AIDecisionLog`) |
| Mini App opens blank or "forbidden" | `MINIAPP_URL` not HTTPS, opened outside Telegram (no initData), or your id not in `ADMIN_USER_IDS` |
| Publishing does nothing / 403 | `ADMIN_USER_IDS` empty or missing your id (fail-closed) |
| WordPress publish fails (401/403) | Wrong `WORDPRESS_USER` / `WORDPRESS_APP_PASSWORD`, or REST API/Application Passwords disabled |
| Channel publish fails | No `ChannelBot` registered (add the bot to the channel as admin) |
| AI generation never finishes (stuck "generating") | worker down, or OpenAI web-search call failing — check worker logs / `ContentDraft.error` |

---

## 11. Pre-launch smoke tests (with real credentials)

- **Support:** as a normal user, DM a KB question → instant grounded answer, mirrored to the group.
  Ask for a personal result → polite hold + escalation card. Reply as staff → it reaches the user and
  pauses the AI. Send a jailbreak/medical prompt → it escalates, never answers.
- **Publishing:** as an allowlisted admin, open ✍️ Kontent → generate an AI post → edit → publish to
  the channel; confirm it arrives. Then an article → WordPress; confirm the post URL.
