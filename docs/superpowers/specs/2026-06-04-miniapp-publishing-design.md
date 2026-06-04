# Mini-App Content Publishing — Design

**Status:** Approved · **Date:** 2026-06-04 · **Subsystem:** 2 of the bot optimization
(independent of the AI Customer Support subsystem; shares the Django project, the LLM client,
the KB snapshot, and the Django-Q queue).

> Bot-facing/user-facing text is Uzbek; this doc is English to match the repo's other docs.

## 1. Problem & Goal

Staff need to publish clinic content without juggling separate tools. From the bot, a staff
member opens a **Telegram Mini App**, composes a **post** or **article** — either **AI-generated**
(researched on the web and adapted to the clinic) or **manual** — reviews/edits it, and publishes
to any combination of **WordPress site / Telegram channel / bot users**. Nothing publishes without
the staff member reviewing it first.

### Non-goals
- No auto-publishing; a human always reviews the body before it goes out.
- No scheduling/calendar (future).
- No rich WYSIWYG editor; a plain editable textarea (Markdown/HTML-light) for v1.
- Not customer-facing — this is a staff tool (allowlisted).

## 2. Decisions (locked)

| Area | Decision |
|---|---|
| UI | **Telegram Mini App** (web form), vanilla JS + Telegram WebApp SDK, served by Django |
| AI research | **OpenAI web-search tool** + clinic-KB grounding (one vendor; reuses our key) |
| WordPress | **REST API** + **Application Password** (HTTP Basic); creds in env |
| Generation latency | **Async** (Django-Q job) + Mini App **polls** for the draft |
| `kind` vs `targets` | `kind` (post/article) = content style/length; `targets` = independent checkboxes |
| WP publish state | Publish as a **live post** (the Mini App preview is the review gate); configurable |
| Access | initData HMAC validation **+ staff allowlist** on every API call |

## 3. Architecture & Modules

New, isolated from the support subsystem.

```
main/pages/
├── publishing/
│   ├── __init__.py
│   ├── auth.py         # validate_init_data(raw) -> telegram_user_id | None  (HMAC + freshness)
│   ├── generator.py    # generate_content(kind, title, reference_link, kb) -> {title, body}
│   ├── publishers.py   # WordPressPublisher / ChannelPublisher / BotUsersPublisher
│   └── service.py      # orchestration: start_generation(), publish_draft()
├── miniapp/
│   ├── __init__.py
│   ├── views.py        # composer page + JSON API (generate / draft-status / publish)
│   └── templates/miniapp/composer.html
├── tasks.py            # + generate_content_job(draft_id)
├── models.py           # + ContentDraft
└── urls.py             # + /miniapp/ routes
```

Each publisher implements the same interface: `publish(draft) -> {"ok": bool, "url"/"count"/"error"}`.
The service is the only thing the API views call; views stay thin.

## 4. Data Model

```
ContentDraft
  created_by      → BotUser (the staff member; from validated initData)
  kind            CharField [post|article]
  mode            CharField [ai|manual]
  title           CharField
  reference_link  URLField (blank; AI mode)
  body            TextField (generated or manual; edited before publish)
  status          CharField [draft|generating|ready|published|failed]
  error           TextField (blank; generation/publish failure detail)
  targets         JSONField  {"site": bool, "channel": bool, "bot_users": bool}
  publish_results JSONField  {"site": {...}, "channel": {...}, "bot_users": {...}}
  created_at / updated_at
```

Drafts are retained for audit; admin can browse them (read-mostly admin).

## 5. End-to-End Flow

1. Staff taps a bot reply-keyboard/inline button **"✍️ Kontent"** → the bot opens the Mini App via a
   `web_app` button pointing at `MINIAPP_URL` (`/miniapp/`).
2. The Mini App loads `Telegram.WebApp.initData` (signed by Telegram) and sends it with **every** API
   request (header `X-Telegram-Init-Data`). The backend `validate_init_data` checks the HMAC and
   `auth_date` freshness, extracts the Telegram user id, and confirms it's in the staff allowlist.
   Invalid → `403`.
3. Form fields: kind, mode, title, reference_link (AI), body (manual), target checkboxes.
4. **AI mode:** `POST /miniapp/api/generate` `{kind, title, reference_link}` → create
   `ContentDraft(status=generating)`, enqueue `generate_content_job(draft_id)`, return `{draft_id}`.
   The Mini App polls `GET /miniapp/api/draft/<id>` (~2s interval) until `status=ready`, then fills
   the editable body box. **Manual mode:** the body box is typed directly (no draft/generation).
5. Staff edits the body, picks targets, taps **Publish** → `POST /miniapp/api/publish`
   `{draft_id?, kind, title, body, targets}` → the service runs each selected publisher, stores
   `publish_results`, sets `status=published` (or `failed` with per-target errors), and returns the
   results (WP URL, channel message link, broadcast count). The Mini App shows per-target status.

## 6. AI Generation (`generator.py`)

`generate_content(kind, title, reference_link, kb_snapshot) -> {"title", "body"}`:
- Calls OpenAI with the **web-search tool** to research `title` (and read `reference_link` if given),
  then writes content **adapted to the clinic** using the KB snapshot (name, services, hours, tone).
- `kind=post` → short, channel-friendly (a few sentences + call to action). `kind=article` →
  long-form, structured (headings, sections) suitable for WordPress.
- Output language: Uzbek. The exact OpenAI web-search API surface is **encapsulated here** (one seam),
  mocked in tests; verify against the current OpenAI SDK at build time.
- This is staff-initiated and staff-reviewed, so the safety bar is "no secret leakage / valid output",
  not the customer-facing guardrail suite.

## 7. Publishers (`publishers.py`)

Common interface `publish(draft) -> dict`:
- **WordPressPublisher:** `POST {WORDPRESS_URL}/wp-json/wp/v2/posts` with
  `Authorization: Basic base64(WORDPRESS_USER:WORDPRESS_APP_PASSWORD)`, body
  `{title, content, status: "publish"}`. Returns `{"ok", "url": resp["link"]}` or `{"ok": False, "error"}`.
- **ChannelPublisher:** `sentMessage` (HTML) to the registered `ChannelBot.chat_id`; returns the
  message link if available.
- **BotUsersPublisher:** broadcast the body to all `BotUser`s (reuses the existing broadcast pattern);
  returns `{"ok", "count"}`.

Each publisher is independent; one failing target doesn't abort the others — results are per-target.

## 8. Telegram initData Auth (`auth.py`)

Per Telegram's Mini App spec:
1. Parse the `initData` query string; pull out `hash`.
2. Build `data_check_string` = the remaining `key=value` pairs sorted by key, joined by `\n`.
3. `secret_key = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN)`.
4. `computed = HMAC_SHA256(key=secret_key, msg=data_check_string)` (hex). Constant-time compare to `hash`.
5. Reject if `auth_date` is older than a TTL (e.g., 24h).
6. Parse the `user` JSON → Telegram user id → must be in the staff allowlist (`ADMIN_USER_IDS`).

This runs on **every** API call. The Mini App API is otherwise public (CSRF-exempt), so this is the
only thing standing between the internet and "publish to our site/channel" — it is load-bearing and
gets dedicated tests (valid, tampered hash, stale auth_date, non-allowlisted user).

## 9. Configuration (env)

```
WORDPRESS_URL=https://clinic.example/        # base; /wp-json/... appended
WORDPRESS_USER=...
WORDPRESS_APP_PASSWORD=...                    # WP Application Password
MINIAPP_URL=https://<public-host>/miniapp/    # HTTPS; ngrok in dev, real domain in prod
# OPENAI_API_KEY, BOT_TOKEN, ADMIN_USER_IDS reused from Phase 1
```
Telegram only loads Mini Apps over HTTPS. WordPress creds live server-side only; the frontend never
sees them.

## 10. Testing

- **auth:** valid initData passes; tampered hash, stale `auth_date`, and non-allowlisted user all `403`.
  (Build a signed fixture with a test bot token.)
- **publishers:** WordPress (mock `requests` → assert URL/headers/payload + parse `link`); channel
  (mock Telegram); bot-users (mock broadcast → assert count). One target failing doesn't break others.
- **generator:** mock the OpenAI seam → assert prompt includes KB + reference link + kind; returns body.
- **service + API:** generate enqueues a job + returns id; draft-status reflects state; publish records
  per-target results. All API endpoints reject unauthenticated requests.
- The HTML/JS is thin; backend holds the logic. No live network in tests.

## 11. Build Order (for the plan)

Backend-first so each step is testable before any UI exists:
1. `ContentDraft` model + admin.
2. `auth.py` (initData validation) — highest security value.
3. `publishers.py` (the three publishers).
4. `generator.py` (AI seam, mocked).
5. `service.py` + `generate_content_job` (orchestration + async).
6. `miniapp/views.py` + URLs (JSON API, auth-gated).
7. `composer.html` (the form + polling JS) + the bot "✍️ Kontent" `web_app` button.

## 12. Out of Scope / Future
- Scheduling, draft collaboration, image upload, WYSIWYG.
- Publishing to WP as a *draft* for a second review tier (currently publishes live after Mini App review).
- Analytics on published content.

## 13. Open Questions
- Exact OpenAI web-search API/tool name — confirm against the current SDK at build (isolated in `generator.py`).
- Channel "message link" is only available for public channels with a username; private channels return
  no public link (we still return the message id).
