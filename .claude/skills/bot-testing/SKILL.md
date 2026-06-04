---
name: bot-testing
description: >-
  Use when writing or running tests for this Telegram bot — testing the getPost
  webhook dispatch, BotUser.status FSM transitions, callbacks, or membership
  gating. Covers mocking outbound Telegram/LLM calls, building update fixtures,
  and the test commands. pages/tests.py is currently empty.
---

# Testing this bot

`main/pages/tests.py` is an empty stub. The bot is testable because all behavior funnels through one view and all outbound calls go through one module.

## Run

From `main/`:

```bash
python manage.py test                                   # all
python manage.py test pages.tests.ClassName.test_method # single test
```

## Strategy

POST crafted Telegram update payloads to `/getpost/` with Django's test `Client`, then assert on DB state and on which Telegram calls were made. The endpoint is `@csrf_exempt`, so no CSRF token is needed.

**Mock the outbound boundary so tests make zero network calls.** Everything outbound lives in `pages/TelegramAPI.py` (`sentMessage`, `answerCallbackQuery`, `getMemberInformation`, `forwardMessage`, `deleteMessage`). Patch these where `views.py` imports them (they are imported into the `pages.views` namespace), or patch `requests.post`. Mock `getMemberInformation` to return `"member"` vs. `""` to simulate subscribed/unsubscribed users.

## Fixtures

Build small factories instead of copy-pasting JSON:

```python
def make_message(text, user_id=1, chat_type="private", **extra):
    return {"message": {
        "message_id": 10, "text": text,
        "from": {"id": user_id, "first_name": "T", "is_bot": False},
        "chat": {"id": user_id, "type": chat_type},
        **extra,
    }}

def make_callback(data, user_id=1):
    return {"callback_query": {
        "id": "cq1", "data": data,
        "from": {"id": user_id},
        "message": {"message_id": 10},
    }}
```

POST with `self.client.post("/getpost/", data=json.dumps(payload), content_type="application/json")`.

## What to cover

1. **FSM transitions** (`BotUser.status`): for each command, assert it sets the right status; then send the follow-up message and assert the side effect + that status resets. Statuses: `getAdmin`, `addingChannel`, `creatingmainpost`, `addingAnswer`, `addingPost`, `addingChannelPost`, `addingPostAnswer`, `addinganswer`.
2. **Update types**: `message` (private vs. group/supergroup/channel via `chat['type']`), `callback_query` (`check`, `done`, `turn_on_subcription`, `turn_off_subcription`, `checkAnswer-<id>`), `my_chat_member` (auto-registers `ChannelBot`/`GroupBot`).
3. **Auth gate**: correct password (`WTlJgvNGS3PZGOv`) promotes admin / activates group; wrong password rejected.
4. **Forced subscription**: subscribed vs. unsubscribed branches (via the mocked membership check).
5. **Single-row config models** (`AboutMessage`, `ChannelMessage`, `AutoAnswer`): test the **empty-table** case — `.all()[0]`/`.first()` on no rows is where `IndexError`/`AttributeError` bugs live.

## Edge cases to probe

- Missing keys in the payload (`KeyError`) — payload shape varies by update type.
- `/start` from a new user vs. an existing user.
- Actions before any `AboutMessage`/`GroupBot` row exists.
- Non-text messages (photo/video `file_id` paths).
- `elif`-order shadowing in the long dispatch chain.

When mocking LLM features (see **llm-integration**), patch the Anthropic client the same way — assert the deterministic fallback fires when the call raises.

When you find a real bug: write the failing test first, then report input → expected → actual. Report coverage honestly — say what you did and did not test.
