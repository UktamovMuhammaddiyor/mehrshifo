---
name: llm-integration
description: >-
  Use when adding Claude/LLM features to this Telegram bot — smart auto-answers,
  support-message classification/routing, content moderation, or generating
  channel-post answers. Covers where AI fits the existing models, calling the
  Anthropic SDK from the synchronous webhook, key handling, and fallbacks.
---

# Adding LLM features to this bot

The bot has **no AI today**. Introduce it where it helps, without breaking the synchronous webhook. For Anthropic SDK specifics (client setup, prompt caching, tool use, model migrations) also invoke the **claude-api** skill.

## Where AI realistically fits

| Surface | Today | With an LLM |
|---|---|---|
| `AutoAnswer` | one static reply to every user | context-aware reply (fall back to static text on failure) |
| Support forwarding to `GroupBot` | blind forward | classify intent/urgency/language, tag or route before forwarding |
| Inbound / broadcast text | none | moderation screen before relay |
| `ChannelMessage.answer` | manually typed hidden answer | LLM-drafted or graded answer |

Confirm which surface you're targeting before building.

## Architecture rules

- **The webhook is synchronous.** `getPost` in `pages/views.py` must return to Telegram quickly, or Telegram times out and retries (causing duplicate handling). A multi-second blocking LLM call inside the handler is a real risk. Options, in order of preference:
  1. Use a fast model and tight prompts; send a `sendChatAction` "typing" first.
  2. Offload to a background path (management command / queue / thread) and reply asynchronously — propose this explicitly with its trade-offs.
  Never silently add seconds of latency to the webhook.
- **Isolate the calls.** Put LLM code in a new `main/pages/llm.py`, mirroring how `pages/TelegramAPI.py` isolates Telegram. Don't scatter SDK calls through `views.py`.
- **Always have a deterministic fallback.** If the API errors or rate-limits, fall back to the existing static behavior (e.g. `AutoAnswer.text` or "Murojatiz qabul qilindi.") so the bot never goes silent. Wrap calls in try/except.
- **Respond in Uzbek.** User-facing output must be Uzbek — instruct the model in the system prompt and verify.

## Keys & dependencies

- Store `ANTHROPIC_API_KEY` in the environment, or in `main/pages/creditionals.py` alongside `BOT_URL`/`URL` (the project's existing secret module — keep the misspelling). Never hardcode or commit keys.
- Add `anthropic` to `requirements.txt` (UTF-16 LE — re-encode to UTF-8 when editing).
- Default to the latest Claude models. Use **prompt caching** for any stable system prompt or few-shot block to cut cost/latency.

## Shape of a feature

Design as a small pure-ish function: `(telegram_text_or_payload) -> result`, with the fallback baked in:

```python
# pages/llm.py
def smart_answer(user_text: str) -> str:
    try:
        # Anthropic call; cache the system prompt
        ...
    except Exception:
        return _static_fallback()
```

Then call it from the relevant branch in `getPost`. Coordinate model/field changes with **django-bot-conventions** (FSM via `BotUser.status`, single-row config models, commit migrations). Hand test scaffolding to the qa-engineer — mock the Anthropic client the same way outbound `requests` are mocked (see **bot-testing**).

Recommend the simplest AI that solves the problem; be explicit about cost, latency, and failure modes.
