# Environments (prod & dev/staging)

This bot runs in two environments that share one codebase. Each machine has its
own `main/.env` file (git-ignored); `settings.py` and `pages/creditionals.py`
read everything from it. There are **two separate Telegram bots** — a live one
for prod and a staging one for dev — so testing never touches real users.

| | **prod** | **dev / staging** |
|---|---|---|
| Where | existing host | your machine + ngrok tunnel |
| `APP_ENV` | `prod` | `staging` |
| `DEBUG` | `False` | `True` |
| Database | `db.sqlite3` (live) | `db.dev.sqlite3` (isolated) |
| Bot | live bot | staging bot (new, via @BotFather) |

## How config resolves

`settings.py` calls `load_dotenv(main/.env)`. Every setting has a default that
reproduces the **original** prod behavior, so **deploying this code to prod with
no `.env` present changes nothing** (`db.sqlite3`, the existing secret key,
`DEBUG=True`). Prod opts into the new behavior by adding its own `.env`.

Variables (full reference + comments in `main/.env.example`):
`APP_ENV`, `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, `BOT_TOKEN`, `WEBHOOK_URL`,
`BOT_ADMIN_PASSWORD`, optional `DB_NAME`.

`BOT_URL` is derived as `https://api.telegram.org/bot<BOT_TOKEN>/`; `URL` (the
webhook target used by `/setwebhook/`) comes from `WEBHOOK_URL`.

### The .env files

Only the file literally named `.env` is auto-loaded. The repo uses:

| File | Tracked? | Purpose |
|---|---|---|
| `main/.env.example` | committed | documented template |
| `main/.env.staging` | git-ignored | staging values (canonical copy) |
| `main/.env.prod` | git-ignored | prod values (canonical copy) |
| `main/.env` | git-ignored | the **active** copy on this machine |

Activate an environment by copying it onto `.env`:
- dev machine: `cp main/.env.staging main/.env`
- prod host:  `cp main/.env.prod main/.env`

Database selection: only `APP_ENV=prod` uses the live `db.sqlite3`; any other
value (e.g. `staging`) uses `db.dev.sqlite3`. `APP_ENV` defaults to `prod`, so a
host with no `.env` still uses the live database.

---

## Set up dev / staging

Steps marked **[you, in Telegram]** are manual and can't be automated.

### 1. Create the staging bot — **[you, in Telegram]**
1. Open [@BotFather](https://t.me/BotFather) → `/newbot` → follow prompts.
2. Copy the **bot token** it gives you.
3. Make the staging bot's settings match the live bot, in particular group
   privacy: `/mybots` → select it → *Bot Settings* → *Group Privacy*. Set it the
   same as the prod bot (typically **Disabled** so it can read group messages).

### 2. Create staging channel + group — **[you, in Telegram]**
1. Create a new **channel** and a new **group** (these are your staging
   equivalents of the prod channel/group).
2. Add the **staging bot as an administrator** to **both**. Adding it as admin is
   what makes the bot auto-register them (`my_chat_member` → `ChannelBot` /
   `GroupBot`) — do this *after* the server + webhook are live (step 6+), or the
   updates are missed.

### 3. Fill in the staging env file
`main/.env.staging` already exists with a generated `SECRET_KEY`, and it is also
the active `main/.env` on this machine (run `cp main/.env.staging main/.env` to
reset it). Edit these in `main/.env`:
- `BOT_TOKEN=` → the staging token from step 1.
- `BOT_ADMIN_PASSWORD=` → pick a staging password (keep it different from prod).
- `WEBHOOK_URL` and `ALLOWED_HOSTS` → filled in step 5 once ngrok is running.

### 4. Install deps & migrate the dev DB
```bash
cd main
python -m venv .venv && source .venv/bin/activate    # if not already
pip install -r requirements.txt                       # now UTF-8; installs cleanly
python manage.py migrate                               # creates db.dev.sqlite3
```

### 5. Start ngrok and point the webhook at it
```bash
ngrok http 8000
```
Copy the `https://<sub>.ngrok-free.app` URL, then in `main/.env` set:
```
ALLOWED_HOSTS=<sub>.ngrok-free.app,127.0.0.1
WEBHOOK_URL=https://<sub>.ngrok-free.app/getpost/
```
> ngrok's free URL changes every restart — re-edit these two lines and re-run
> step 6's `/setwebhook/` each time it changes.

### 6. Run the server and register the webhook
```bash
python manage.py runserver
```
Then open **`http://127.0.0.1:8000/setwebhook/`** once. It tells Telegram to POST
updates for the staging bot to your ngrok `/getpost/`. A success response means
the webhook is live.

### 7. Wire up the bot — **[you, in Telegram]**
1. `/start` the staging bot.
2. `/getadmin` → send your staging `BOT_ADMIN_PASSWORD` → you get the admin menu.
3. Add the staging bot as admin to the channel (step 2) — it auto-registers.
   Then `/addchannel` and send the channel's `@username` to attach it.
4. Add the staging bot as admin to the group — it auto-registers and replies
   asking for a password. **Reply to that message** with `BOT_ADMIN_PASSWORD` to
   activate the group (this is where support messages get forwarded).
5. Send a normal message as a non-admin user to confirm the end-to-end flow.

---

## Set up prod

Do this on the live host. Nothing here is destructive if you keep the existing
secret key.

1. Fill in `main/.env.prod`. It already has `APP_ENV=prod`, `DEBUG=False`, the
   existing prod `SECRET_KEY` (reused so admin sessions survive — rotate later if
   you want), and the current `BOT_ADMIN_PASSWORD`. Set the three placeholders:
   `ALLOWED_HOSTS` (prod domain), `BOT_TOKEN` (live bot), and `WEBHOOK_URL`
   (`https://<prod-domain>/getpost/`).
2. Activate it on the prod host: `cp main/.env.prod main/.env`.
3. `pip install -r requirements.txt` (adds `python-dotenv`).
4. Restart the prod app/service. `APP_ENV=prod` keeps it on the live `db.sqlite3`.
5. You generally do **not** need to re-run `/setwebhook/` — the prod webhook URL
   is unchanged. Only re-run it if `WEBHOOK_URL` changed.

> Zero-downtime path: deploy the code first (prod keeps running on defaults), then
> add `.env` and restart when you're ready to flip `DEBUG` off.

---

## Notes & gotchas

- **Never commit `main/.env*`** (except `.env.example`) — `.env`, `.env.staging`,
  and `.env.prod` are all git-ignored; only `.env.example` is committed.
- `db.dev.sqlite3` is git-ignored; the live `db.sqlite3` is never read in dev.
- Running the test suite (`python manage.py test`) uses Django's in-memory test
  DB and mocks Telegram, so it needs no live bot — but it does read
  `BOT_ADMIN_PASSWORD` from whatever `.env` is active.
- The two bots are independent tokens; staging actions can't reach prod chats.

## Completion checklist
- [ ] Staging bot created in @BotFather; token in `main/.env`
- [ ] Staging bot group-privacy set to match prod
- [ ] Staging channel + group created
- [ ] `BOT_ADMIN_PASSWORD` set to a staging value in `.env`
- [ ] `pip install -r requirements.txt` run; `migrate` created `db.dev.sqlite3`
- [ ] ngrok running; `ALLOWED_HOSTS` + `WEBHOOK_URL` updated
- [ ] `runserver` up; `/setwebhook/` returned success
- [ ] Bot added as admin to channel + group (auto-registered)
- [ ] `/getadmin` worked; channel attached; group activated by password
- [ ] (prod) `.env.prod` filled and copied to `.env` on the live host (`DEBUG=False`)
