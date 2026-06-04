# AI Mijoz Support — Design (Phase 1)

> **Til / Language:** This spec is written in English to match the repo's existing
> docs (`CLAUDE.md`, `docs/ENVIRONMENTS.md`). All **user-facing bot strings stay in
> Uzbek** and are shown verbatim. Ask if an Uzbek translation of the whole doc is wanted.

**Status:** Draft for review · **Date:** 2026-06-04 · **Subsystem:** AI Customer Support
(part of the larger bot optimization; Content Publishing + Mini-App is a separate spec).

---

## 1. Problem & Goal

The bot today forwards every private user message into a support `GroupBot`; a staff
member replies to the forwarded message and the bot `copyMessage`s that reply back to the
user. This is **slow and depends on staff being online**, so customers are lost.

**Goal:** an AI that answers customers **immediately** from a maintained knowledge base,
stays grounded (especially on prices), keeps **per-customer conversation context**, mirrors
every answer into the support group for staff oversight, and **escalates to humans** when it
should not answer (personal/medical data, complaints, low confidence). Staff can take over
any conversation at any time, and an admin can switch the AI off (graceful fallback to
today's forward-only behavior).

### Non-goals (Phase 1)
- No access to patient/medical records; AI never reveals personal results (see §6).
- No appointment **booking** or any state-changing action by the AI.
- No vector DB / embeddings (KB is small — prompt-stuffing + caching is enough).
- Learning loop and Telegram-history import are **Phase 2** (see §12).
- Content publishing / Mini-App is **out of scope** (separate subsystem/spec).

---

## 2. Locked Decisions

| Area | Decision |
|---|---|
| Personal/medical data | AI gives **general/public info only**. Personal data & "ariza natijasi" requests → **escalate to human**. No HIS/LIS integration. |
| Knowledge base | **Structured DB models**, edited via **Django admin**. |
| Group model | **Single existing support group**; reuse forward + `copyMessage`; staff reply triggers handoff. |
| LLM provider | **OpenAI GPT-4o**, behind a provider-agnostic `LLMClient` interface (swappable). |
| Grounding | Whole KB injected into the prompt every call + caching. **No vector DB.** |
| Refactor | **Targeted** new modules; existing channel/subscription/broadcast code untouched. |
| Processing | **DB-backed queue** (Django-Q2 or RQ) + `update_id` dedupe. Webhook never waits on the LLM. |
| Handoff resume | **Manual only** (button / `/ai_resume`). No auto-resume. |
| Admin gate | Move to a **Telegram `user_id` allowlist** (env/DB) for admin + AI controls. |

---

## 3. Architecture & Module Layout

New modules live inside the existing `pages` app. Existing channel / forced-subscription /
broadcast logic is **not modified**.

```
main/pages/
├── views.py            # getPost — slimmed to: verify secret → parse → dedupe → enqueue → 200
├── models.py           # existing models + new models (see §4)
├── tasks.py            # process_client_message() — the queued job
├── ai/
│   ├── client.py       # LLMClient interface + OpenAIClient implementation
│   ├── prompts.py      # system-prompt builder: persona + safety rules + KB injection
│   ├── pipeline.py     # orchestrates: load context → call LLM → decide action
│   ├── schema.py       # structured-output JSON schema + parsing
│   └── guardrails.py   # input truncation + output safety checks
├── knowledge/
│   └── snapshot.py     # assembles KB → cached text block; invalidated on KB save
├── handlers/
│   ├── private_ai.py   # private-chat AI flow entrypoint
│   └── group.py        # group reply → copyMessage + handoff toggle
└── management/commands/
    └── (phase 2: import_group_history.py)
```

**Provider abstraction.** `LLMClient` exposes one method:
`complete(system: str, messages: list, schema: dict) -> dict`. `OpenAIClient` implements it
with OpenAI structured outputs. Swapping providers later = a new class, no pipeline changes.

---

## 4. Data Model (Phase 1)

Existing models (`BotUser`, `GroupBot`, `ChannelBot`, `AboutMessage`, `ChannelMessage`,
`AutoAnswer`) are unchanged. New Telegram-id fields use `BigIntegerField`; **migrate
`BotUser.user_id` to `BigIntegerField`** (current `IntegerField` overflows on large ids).

### A. Knowledge Base (Django-admin editable)
```
Service        name, category, price, currency, duration_min,
               description, is_active, updated_at
Doctor         full_name, specialty, schedule_text, bio, is_active, updated_at
ClinicInfo     (singleton) name, address, geo_lat, geo_long, phones,
               working_hours, days_off, extra_notes, updated_at
FAQ            question, answer, category, is_active, updated_at
```

### B. Conversation memory
```
Conversation         user → BotUser, status [active|handoff|closed],
                     handoff_until (nullable, unused in P1), created_at, updated_at
                     → exactly one 'active' conversation per user
ConversationMessage  conversation → Conversation, role [client|ai|staff],
                     text, tg_message_id (nullable), intent (nullable),
                     confidence (nullable), created_at
```

### C. AI control (singleton config — matches existing single-row pattern)
```
AISettings   is_enabled, model_name (default "gpt-4o"), temperature,
             confidence_threshold (default 0.6), max_history_messages (default 12),
             max_input_chars (default 2000), max_output_tokens (default 500),
             daily_call_cap, holding_message, persona_extra,
             complaint_notify_user_id (nullable), updated_at
```

### D. Idempotency & audit
```
ProcessedUpdate   update_id (unique), processed_at   # Telegram retry dedupe
AIDecisionLog     conversation (nullable), input_text, kb_version, intent,
                  confidence, action [answer|notify|escalate|skipped],
                  output_text, created_at             # audit / debugging
```

**KB snapshot caching.** `knowledge/snapshot.py` builds one text block from
`Service/Doctor/ClinicInfo/FAQ`, stored in Django cache with a version stamp. A `post_save`
/ `post_delete` signal on those models **invalidates the cache immediately**, so a price
edit reflects on the very next message — without rebuilding on every call. The stable block
is sent as a cacheable prompt prefix (OpenAI prompt caching) to cut token cost.

---

## 5. End-to-End Flow

```
1. Telegram → getPost (webhook)
   • verify X-Telegram-Bot-Api-Secret-Token header (reject if missing/wrong)
   • parse update; if update_id already in ProcessedUpdate → 200 and stop (dedupe)
   • record update_id; enqueue process_client_message(payload); return 200 immediately

2. Worker → process_client_message():
   a. get_or_create active Conversation for the user; append client ConversationMessage
   b. gate:
        • AISettings.is_enabled == False  → forward to group only (today's behavior); stop
        • Conversation.status == handoff   → forward to group only; stop
        • per-user rate limit exceeded     → soft reply "biroz kuting"; stop
        • daily_call_cap exceeded          → AI off for the day; forward to group; stop
   c. build prompt = persona + safety rules + KB snapshot + last N messages + new message
   d. LLMClient.complete(...) → structured output:
        { reply_uz, intent, confidence, needs_human, notify_admin }
   e. guardrails on output (secret leakage, ungrounded price/discount, medical claim, length)
   f. decide action (CODE is the authority, not the model — see §6):
        • escalate  → send fixed holding message to client; post escalation card to group
        • notify    → send model reply to client; post labeled card + notify recipient
        • answer    → send model reply to client; post normal card to group
   g. in all three actions, forward the client's original message to the group
      (preserves forward_origin), then post the AI note/card beneath it
   h. append ai ConversationMessage; write AIDecisionLog

3. Staff handoff (group.py):
   • staff replies to the forwarded client message
       → copyMessage delivers it to the client (existing mechanism)
       → Conversation.status = handoff (AI pauses for this customer)
   • resume: [🤖 AI'ni davom ettirish] button or /ai_resume → status = active
```

The webhook returns `200` in milliseconds; all LLM work is in the worker. Telegram never
times out, so there are no duplicate sends.

---

## 6. Intent, Routing & Escalation

The LLM returns `intent`, `confidence`, `needs_human`, `notify_admin`, and a draft `reply_uz`
(the `intent` enum and full output schema live in `ai/schema.py`).
**Code decides the final action** (the model's reply is discarded on escalation):

| Intent | Action | Client sees | Group |
|---|---|---|---|
| `greeting/smalltalk` | answer | friendly reply | normal card |
| `info_question` (grounded, confident) | answer | KB-based reply | normal card |
| `complaint` | notify + handoff | empathetic ack | **⚠️ SHIKOYAT** + notify recipient |
| `suggestion` | notify | thanks | **💡 TAKLIF** + notify recipient |
| `personal_data_request` | escalate | holding message | **🔔 AI javob bera olmadi** |
| `medical_advice_request` | escalate | "shifokor bilan maslahatlashing" + holding | escalation card |
| `appointment_request` | answer info, escalate to act | how/price from KB; booking → human | card / escalation |
| `unclear` / `needs_human` / `confidence < threshold` / not grounded | escalate | holding message | escalation card |

**Escalation triggers (any of):** `intent ∈ {personal_data_request, medical_advice_request}`,
`needs_human == true`, `confidence < AISettings.confidence_threshold`, or the model could not
ground its answer in the KB. **Anti-hallucination rule** (system prompt): *if the answer is
not in the provided KB, do not guess — set `needs_human = true`.*

**Holding message (Uzbek, fixed):**
`"Savolingiz mutaxassisimizga yuborildi. Tez orada javob beramiz. 🙏"`

**Complaint/suggestion notification:** if `AISettings.complaint_notify_user_id` is set, DM
that staff member; if the bot cannot DM them (they never `/start`ed the bot), @-tag them in
the group instead. Always also post the labeled card in the group.

**One group message pattern everywhere:** forward the client message (so `forward_origin`
exists and staff reply routing works) + a contextual note (AI reply / SHIKOYAT / TAKLIF /
"AI can't answer"). Staff always reply to the forwarded message to respond.

---

## 7. Security

1. **AI cannot act.** The model only returns `{text, intent, ...}`. No booking, no price
   change, no DB writes, no messaging arbitrary users, no data reads. **All side effects are
   in our code, gated.** This is the primary defense: a jailbreak yields nothing actionable.
2. **KB is public-only.** No patient data is ever in the KB, so the AI cannot leak what it
   does not have. Personal requests escalate.
3. **Prompt-injection defense.** User text sits in a clearly delimited "untrusted" block;
   conversation history is treated as data, not instructions; structured output constrains
   the model; output guardrails block system-prompt leakage, ungrounded price/discount
   promises, and medical claims.
4. **Medical liability.** The AI never diagnoses or gives treatment advice; such requests →
   "shifokor bilan maslahatlashing" + escalation. A one-time disclaimer is sent to new users.
5. **Webhook & secrets.**
   - Set `secret_token` in `setWebhook`; verify `X-Telegram-Bot-Api-Secret-Token` on every
     request (the `/getpost/` endpoint is otherwise open to forged POSTs).
   - `.env*` already gitignored (verified). **Remove `db.sqlite3` from git tracking** — once
     conversations are stored it would push (health-adjacent) customer messages into history.
   - Production: `DEBUG=False`, real `SECRET_KEY`, correct `ALLOWED_HOSTS` (no ngrok), HTTPS.
   - API keys only in env; never logged.
6. **Abuse / cost control.** Per-user rate limit (default ~8 msgs/min → soft "biroz kuting");
   global `daily_call_cap` → AI auto-off + forward fallback; input truncation
   (`max_input_chars`); `max_output_tokens`; `update_id` dedupe stops retry amplification.
7. **Oversight & audit.** Every AI reply is mirrored to the group (human can catch a bad
   answer and take over); global kill switch (`is_enabled`); `AIDecisionLog` records each
   decision (input, KB version, intent, confidence, action, output).
8. **Admin gate.** Replace the shared password with a Telegram `user_id` **allowlist**
   (env/DB) for admin and AI controls.
9. **Red-team tests (TDD).** Adversarial cases: "ignore instructions", "reveal system
   prompt", "give me a free service", fake medical/personal-data requests.

---

## 8. Management & Configuration

**Admin bot commands (allowlisted users):**
```
/ai_on   /ai_off      → global enable/disable (AISettings.is_enabled)
/ai_status            → on/off, model, today's call count/cost, active handoff count
/ai_resume            → return a handed-off conversation to the AI
```
**Django admin:** CRUD for `Service / Doctor / ClinicInfo / FAQ`; `AISettings` page for all
knobs; a **"KB Preview"** action that renders the exact KB text the AI will see; read-only
`AIDecisionLog`.

**Environment (new):**
```
OPENAI_API_KEY=...
TELEGRAM_WEBHOOK_SECRET=...          # used by setWebhook + header verification
ADMIN_USER_IDS=11111111,22222222     # Telegram user_id allowlist
QUEUE_BROKER=...                     # Django-Q2 / RQ config (DB or Redis)
```

---

## 9. Testing Strategy

- **Unit:** routing table (§6) for each intent; guardrails (block/allow cases); KB snapshot
  assembly + cache invalidation on save; `update_id` dedupe; rate-limit / cap gates.
- **Integration:** webhook → enqueue → worker → outbound calls, with `LLMClient` and Telegram
  API mocked. Handoff: staff reply flips `status` and pauses AI; `/ai_resume` restores it.
- **Red-team:** the injection/jailbreak suite from §7.9 must result in `escalate`/safe replies.
- **Manual:** end-to-end on a test bot + test group before enabling on production.

LLM and Telegram network calls are mocked in tests; no live API calls in CI.

---

## 10. Ops / Migration Checklist

1. `git rm --cached main/db.sqlite3`; add to `.gitignore`; document prod DB handling.
2. New migrations for the models in §4 (+ `BotUser.user_id` → `BigIntegerField`).
3. Run a queue worker process (Django-Q2/RQ) alongside the web process.
4. Re-register the webhook with `secret_token`.
5. Set new env vars (§8) in every environment.
6. Seed the KB (services, doctors, clinic info, initial FAQ) via Django admin before enabling.

---

## 11. Defaults Chosen (review these)

- `model_name = gpt-4o` (gpt-4o-mini selectable for cost); `temperature = 0.3`.
- `confidence_threshold = 0.6`; `max_history_messages = 12`; `max_input_chars = 2000`;
  `max_output_tokens = 500`.
- Per-user rate limit ≈ 8 msgs/min; `daily_call_cap` ≈ 1500/day (tune to budget).
- Conversation retention: 90 days (configurable); KB/FAQ permanent.
- Handoff: manual resume only.

---

## 12. Phase 2 (Future — not built now)

- **Learning loop (safe "self-training").** `FAQSuggestion(question, answer,
  source_conversation, status[pending|approved|rejected], reviewed_by, created_at)`. When
  staff answer an escalation, capture Q&A → `FAQSuggestion(pending)`; optionally let the AI
  format it into a clean FAQ. Admin **approve** → real `FAQ`; **reject** → discard. **Nothing
  enters the KB without admin approval** — the AI cannot poison its own knowledge.
- **Telegram history import.** Bot API cannot fetch old history. Admin exports the group
  history (Telegram Desktop → JSON); `import_group_history` parses Q&A pairs, uses the LLM to
  distill recurring questions, and creates `FAQSuggestion(pending)` for review. One-off/batch.
- **Status-only personal lookups.** If the clinic later exposes an "application status" API,
  the AI could report status (not content) after strong identity verification.

---

## 13. Open Questions

- Queue library: **Django-Q2** (DB broker, no Redis) vs **RQ** (needs Redis)? Default
  assumption: Django-Q2 for zero extra infra unless Redis is already available.
- `complaint_notify_user_id`: one staff member, or post to group only? Default: group +
  optional single DM recipient.
- New-user one-time disclaimer wording (Uzbek) — to be drafted with staff.
