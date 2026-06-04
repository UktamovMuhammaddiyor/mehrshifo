---
name: telegram-bot-api
description: >-
  Use when calling the Telegram Bot API in this project — sending messages,
  inline keyboards/callbacks, checking channel membership, forwarding/deleting
  messages, or setting up the webhook. Covers the pages/TelegramAPI.py wrappers,
  the reply_markup shorthand, credentials, and the update payload shapes.
---

# Telegram Bot API in this project

All Telegram interaction is wrapped in `main/pages/TelegramAPI.py`. **Add new Bot API methods there as thin functions — do not inline `requests.post` in `views.py`.**

## Credentials

`main/pages/creditionals.py` (original misspelling — keep it) must define:

- `BOT_URL` — API base ending in a slash: `https://api.telegram.org/bot<TOKEN>/`
- `URL` — the public HTTPS URL Telegram POSTs updates to (the `/getpost/` endpoint)

The file is committed empty; it must be populated locally. Telegram requires a public HTTPS webhook — dev uses an ngrok tunnel, so add the tunnel host to `ALLOWED_HOSTS` in `main/main/settings.py`.

## Existing wrappers

| Function | Bot API method | Notes |
|---|---|---|
| `sentMessage(message_type, chat_id, text, reply_markup={}, parse_mode='HTML', link='', file_id="")` | `sendMessage` / `sendPhoto` | `message_type` is `"Message"`, `"Photo"`, or other (treated as video). Returns parsed JSON. |
| `answerCallbackQuery(callback_query_id, text, show_alert=False, url="")` | `answerCallbackQuery` | Responds to inline-button presses; `show_alert=True` shows a popup. |
| `getMemberInformation(chat_id, user_id)` | `getChatMember` | Returns the status **string** (`member`/`creator`/`administrator`/...) or `""`. |
| `forwardMessage(chat_id, from_chat_id, message_id)` | `forwardMessage` | |
| `deleteMessage(chat_id, message_id)` | `deleteMessage` | |

Membership checks use the helper `userHasMemberOfChannel(chat_id, user_id)` in `views.py`, which treats `member`/`creator`/`admin` as subscribed.

## Inline keyboard shorthand

`sentMessage` accepts a list shorthand for `reply_markup` that it expands into Telegram keyboard JSON:

```python
sentMessage("Message", user_id, "text",
    ['inline_keyboard', [
        [["Kanalga azo bo'lish", 'member', 'https://t.me/...']],   # row 1: one button (text, callback_data, url)
        [["Tekshirish", 'check', '']],                              # row 2
    ]])
```

Each inner triple is `[text, callback_data, url]`. The matching `callback_query` handler in `getPost` branches on `data` (e.g. `check`, `done`, `turn_on_subcription`, or prefix `checkAnswer-<id>`).

A plain reply keyboard (the admin menu) is built as a normal dict and passed via a direct `requests.post` to `sendMessage` with `reply_markup=json.dumps(...)`.

## Update payload shapes (what arrives at `/getpost/`)

The webhook body is JSON; `getPost` branches on the top-level key:

- `message` → has `chat['type']` (`private` / `group` / `supergroup` / `channel`), `from['id']`, `text` or media (`photo`/`video` with `file_id`), `message_id`, optional `reply_to_message`.
- `callback_query` → `data`, `id`, `from['id']`, `message['message_id']`.
- `my_chat_member` → `chat` and `new_chat_member['status']`; fired when the bot's membership/role changes (used to auto-register channels and groups).

Guard with `if 'key' in response` before indexing — payloads vary by update type, and missing-key `KeyError`s are the most common bug.

## Webhook registration

Hit `GET /setwebhook/` once after deploy/tunnel change; the `setWebHook` view calls Telegram's `setWebhook` with `URL`.

Full Telegram Bot API reference: https://core.telegram.org/bots/api
