# AI Customer Support — Phase 2 Implementation Plan (learning loop + history import)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let the clinic's AI improve over time — safely. Capture staff answers to escalated questions as **pending FAQ suggestions** (admin approves → becomes a real FAQ the AI then uses), and provide a one-off command to seed suggestions from an exported Telegram group history. **Nothing enters the KB without admin approval**, and personal/medical Q&A is never captured.

**Architecture:** A new `FAQSuggestion` model (pending/approved/rejected). A capture hook in `group.handle_group_message` creates a pending suggestion from (last customer question, staff reply) — but only when the escalation was a general knowledge gap (the latest `AIDecisionLog.intent` is NOT personal/medical). A Django admin action turns approved suggestions into `FAQ` rows. A `import_group_history` management command parses a Telegram Desktop JSON export and creates pending suggestions by reply-pairing.

**Tech Stack:** Django 5.0.1, Python 3.13, SQLite, Django `TestCase`. Builds on the Phase 1 subsystem (models, `pages/handlers/group.py`, `AIDecisionLog`, `FAQ`).

---

## Conventions
- Commands from `main/` with the venv: `cd main && source .venv/bin/activate` (or `.venv/bin/python`).
- Tests: `python manage.py test pages.tests.<module> -v 2`. Telegram/OpenAI boundaries are mocked.
- Every commit message ends with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Branch: `updates` (do not switch). Per-task commits are pre-authorized.
- Full suite is currently 85 tests, OK — keep it green.

---

## Task 1: `FAQSuggestion` model + admin approve/reject

**Files:**
- Modify: `main/pages/models.py`
- Modify: `main/pages/admin.py`
- Test: `main/pages/tests/test_faq_suggestion.py`

- [ ] **Step 1: Write the failing test**

`pages/tests/test_faq_suggestion.py`:

```python
from django.test import TestCase
from pages.models import FAQSuggestion, FAQ


class FAQSuggestionTests(TestCase):
    def test_defaults_to_pending(self):
        s = FAQSuggestion.objects.create(question="Ish vaqti?", answer="09:00-18:00")
        self.assertEqual(s.status, "pending")
        self.assertIsNone(s.reviewed_by)

    def test_approve_creates_faq_and_marks_approved(self):
        s = FAQSuggestion.objects.create(question="Narx?", answer="150000 UZS")
        faq = s.approve(reviewer="admin")
        self.assertIsInstance(faq, FAQ)
        self.assertEqual(faq.question, "Narx?")
        self.assertEqual(faq.answer, "150000 UZS")
        s.refresh_from_db()
        self.assertEqual(s.status, "approved")
        self.assertEqual(s.reviewed_by, "admin")

    def test_approve_is_idempotent(self):
        s = FAQSuggestion.objects.create(question="Q", answer="A")
        s.approve(reviewer="x")
        s.approve(reviewer="x")  # second call must not create a duplicate FAQ
        self.assertEqual(FAQ.objects.filter(question="Q").count(), 1)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python manage.py test pages.tests.test_faq_suggestion -v 2`
Expected: FAIL — `ImportError: cannot import name 'FAQSuggestion'`.

- [ ] **Step 3: Add the model to `pages/models.py`**

Append:

```python
class FAQSuggestion(models.Model):
    STATUS_CHOICES = [("pending", "pending"), ("approved", "approved"), ("rejected", "rejected")]
    question = models.CharField(max_length=512)
    answer = models.TextField()
    source_conversation = models.ForeignKey(
        "Conversation", null=True, blank=True, on_delete=models.SET_NULL
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    reviewed_by = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"[{self.status}] {self.question}"

    def approve(self, reviewer=""):
        """Create a real FAQ from this suggestion (idempotent) and mark approved."""
        faq, _ = FAQ.objects.get_or_create(
            question=self.question, defaults={"answer": self.answer}
        )
        self.status = "approved"
        self.reviewed_by = reviewer or None
        self.save(update_fields=["status", "reviewed_by"])
        return faq
```

- [ ] **Step 4: Register in `pages/admin.py` with approve/reject actions**

Append:

```python
from .models import FAQSuggestion


@admin.action(description="Approve → create FAQ")
def approve_suggestions(modeladmin, request, queryset):
    for s in queryset.filter(status="pending"):
        s.approve(reviewer=request.user.get_username())


@admin.action(description="Reject")
def reject_suggestions(modeladmin, request, queryset):
    queryset.update(status="rejected", reviewed_by=request.user.get_username())


@admin.register(FAQSuggestion)
class FAQSuggestionAdmin(admin.ModelAdmin):
    list_display = ("question", "status", "reviewed_by", "created_at")
    list_filter = ("status",)
    search_fields = ("question", "answer")
    actions = [approve_suggestions, reject_suggestions]
```

- [ ] **Step 5: Migrate**

```bash
python manage.py makemigrations pages
python manage.py migrate
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python manage.py test pages.tests.test_faq_suggestion -v 2` → PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add main/pages/models.py main/pages/admin.py main/pages/migrations/
git commit -m "feat: FAQSuggestion model with admin approve/reject"
```

---

## Task 2: Capture staff answers to escalations as pending suggestions

**Files:**
- Modify: `main/pages/handlers/group.py`
- Test: `main/pages/tests/test_learning_capture.py`

**Privacy rule:** capture ONLY when the conversation's latest `AIDecisionLog.intent` is NOT `personal_data_request` or `medical_advice_request`. Never store personal/medical Q&A as a suggestion.

- [ ] **Step 1: Write the failing test**

`pages/tests/test_learning_capture.py`:

```python
from unittest import mock
from django.test import TestCase
from pages.models import (
    BotUser, Conversation, ConversationMessage, AIDecisionLog, FAQSuggestion,
)
from pages.handlers import group as group_handler


def staff_reply(target_user_id, text, group_id=-100, message_id=42):
    return {
        "chat": {"id": group_id, "type": "supergroup"},
        "message_id": message_id,
        "text": text,
        "reply_to_message": {
            "message_id": 7, "from": {"is_bot": True},
            "forward_origin": {"type": "user", "sender_user": {"id": target_user_id}},
        },
    }


class LearningCaptureTests(TestCase):
    def setUp(self):
        self.user = BotUser.objects.create(name="Mijoz", user_id=555, user_name="m")
        self.conv = Conversation.active_for(self.user)
        ConversationMessage.objects.create(conversation=self.conv, role="client",
                                            text="Tahlil narxi qancha?")

    @mock.patch("pages.TelegramAPI.copyMessage")
    def test_captures_general_escalation(self, copy):
        AIDecisionLog.objects.create(conversation=self.conv, intent="info_question",
                                     action="escalate", confidence=0.2)
        group_handler.handle_group_message(staff_reply(555, "Umumiy tahlil 80000 UZS"))
        s = FAQSuggestion.objects.get()
        self.assertEqual(s.question, "Tahlil narxi qancha?")
        self.assertEqual(s.answer, "Umumiy tahlil 80000 UZS")
        self.assertEqual(s.status, "pending")

    @mock.patch("pages.TelegramAPI.copyMessage")
    def test_does_not_capture_personal_data(self, copy):
        AIDecisionLog.objects.create(conversation=self.conv, intent="personal_data_request",
                                     action="escalate", confidence=0.9)
        group_handler.handle_group_message(staff_reply(555, "Sizning natijangiz tayyor"))
        self.assertEqual(FAQSuggestion.objects.count(), 0)

    @mock.patch("pages.TelegramAPI.copyMessage")
    def test_ai_resume_does_not_capture(self, copy):
        group_handler.handle_group_message(staff_reply(555, "/ai_resume"))
        self.assertEqual(FAQSuggestion.objects.count(), 0)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python manage.py test pages.tests.test_learning_capture -v 2`
Expected: FAIL (suggestions not created / created for personal data).

- [ ] **Step 3: Add the capture to `group.py`**

In `pages/handlers/group.py`, add a helper and call it on the staff-reply path (after `copyMessage` + handoff, NOT on the `/ai_resume` path):

```python
EXCLUDED_INTENTS = {"personal_data_request", "medical_advice_request"}


def _maybe_capture_suggestion(target_user_id, answer_text):
    """Capture (last customer question, staff answer) as a pending FAQ suggestion,
    unless the latest escalation was personal/medical (privacy)."""
    from ..models import BotUser, Conversation, ConversationMessage, AIDecisionLog, FAQSuggestion
    answer_text = (answer_text or "").strip()
    if not answer_text:
        return
    try:
        user = BotUser.objects.get(user_id=target_user_id)
    except BotUser.DoesNotExist:
        return
    conv = Conversation.active_for(user)
    last_decision = AIDecisionLog.objects.filter(conversation=conv).order_by("-id").first()
    if last_decision and last_decision.intent in EXCLUDED_INTENTS:
        return
    question = (
        ConversationMessage.objects.filter(conversation=conv, role="client")
        .order_by("-id").values_list("text", flat=True).first()
    )
    if not question:
        return
    FAQSuggestion.objects.get_or_create(
        question=question, answer=answer_text,
        defaults={"source_conversation": conv, "status": "pending"},
    )
```

Then, in `handle_group_message`, in the staff-relay branch (the one that calls `copyMessage` + `_set_status(target_user_id, "handoff")`), add immediately after setting handoff:

```python
    _maybe_capture_suggestion(target_user_id, response.get("text") or response.get("caption"))
```

(Do NOT call it on the `/ai_resume` branch.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `python manage.py test pages.tests.test_learning_capture -v 2` → PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add main/pages/handlers/group.py main/pages/tests/test_learning_capture.py
git commit -m "feat: capture staff escalation answers as pending FAQ suggestions (privacy-gated)"
```

---

## Task 3: `import_group_history` command (Telegram export → pending suggestions)

**Files:**
- Create: `main/pages/management/commands/import_group_history.py`
- Test: `main/pages/tests/test_import_history.py`

Deterministic v1: parse a Telegram Desktop JSON export, pair each reply with the message it replies to → `(question=replied-to text, answer=reply text)` → `FAQSuggestion(pending)`. (LLM distillation of recurring questions is a future enhancement.)

- [ ] **Step 1: Write the failing test**

`pages/tests/test_import_history.py`:

```python
import json
import tempfile
from django.test import TestCase
from django.core.management import call_command
from pages.models import FAQSuggestion


class ImportHistoryTests(TestCase):
    def _write(self, data):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, f)
        f.close()
        return f.name

    def test_reply_pairs_become_pending_suggestions(self):
        path = self._write({"messages": [
            {"id": 1, "type": "message", "text": "Ish vaqti qachon?"},
            {"id": 2, "type": "message", "text": "09:00 dan 18:00 gacha", "reply_to_message_id": 1},
            {"id": 3, "type": "message", "text": "Rahmat"},  # no reply → ignored
        ]})
        call_command("import_group_history", path)
        s = FAQSuggestion.objects.get()
        self.assertEqual(s.question, "Ish vaqti qachon?")
        self.assertEqual(s.answer, "09:00 dan 18:00 gacha")
        self.assertEqual(s.status, "pending")

    def test_handles_entity_list_text_and_dedupes(self):
        msgs = {"messages": [
            {"id": 1, "text": ["Manzil ", {"type": "bold", "text": "qayerda"}, "?"]},
            {"id": 2, "text": "Chilonzor 5", "reply_to_message_id": 1},
        ]}
        path = self._write(msgs)
        call_command("import_group_history", path)
        call_command("import_group_history", path)  # re-run must not duplicate
        self.assertEqual(FAQSuggestion.objects.filter(question="Manzil qayerda?").count(), 1)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python manage.py test pages.tests.test_import_history -v 2`
Expected: FAIL — `CommandError: Unknown command 'import_group_history'`.

- [ ] **Step 3: Write the command**

`pages/management/commands/import_group_history.py`:

```python
import json

from django.core.management.base import BaseCommand, CommandError

from pages.models import FAQSuggestion


def _flatten_text(text):
    """Telegram export 'text' is a string or a list of strings/entity dicts."""
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        parts = []
        for chunk in text:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict):
                parts.append(chunk.get("text", ""))
        return "".join(parts)
    return ""


class Command(BaseCommand):
    help = "Import a Telegram Desktop JSON export; reply-pairs become pending FAQ suggestions."

    def add_arguments(self, parser):
        parser.add_argument("json_path")

    def handle(self, *args, **options):
        try:
            with open(options["json_path"], encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Cannot read export: {exc}")

        messages = data.get("messages", [])
        by_id = {m.get("id"): m for m in messages if "id" in m}
        created = 0
        for m in messages:
            parent_id = m.get("reply_to_message_id")
            if parent_id is None or parent_id not in by_id:
                continue
            question = _flatten_text(by_id[parent_id].get("text", "")).strip()
            answer = _flatten_text(m.get("text", "")).strip()
            if not question or not answer:
                continue
            _, was_created = FAQSuggestion.objects.get_or_create(
                question=question, answer=answer, defaults={"status": "pending"}
            )
            created += int(was_created)
        self.stdout.write(f"Created {created} pending FAQ suggestion(s).")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python manage.py test pages.tests.test_import_history -v 2` → PASS (2 tests).

- [ ] **Step 5: Run the full suite**

Run: `python manage.py test pages -v 1` → all PASS (was 85; now ~93 with the 8 new tests).

- [ ] **Step 6: Commit**

```bash
git add main/pages/management/commands/import_group_history.py main/pages/tests/test_import_history.py
git commit -m "feat: import_group_history command seeds FAQ suggestions from Telegram export"
```

---

## Notes / future
- LLM distillation of recurring questions from history (cluster + summarize) is a future enhancement; v1 is deterministic reply-pairing.
- Suggestions are reviewed in Django admin (Task 1's actions). Nothing reaches the live KB without an admin approving it.
