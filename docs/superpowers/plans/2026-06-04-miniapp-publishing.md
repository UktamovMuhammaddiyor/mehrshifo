# Mini-App Content Publishing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** A Telegram Mini App, launched from the bot, where staff compose a post/article (AI-generated with web search + clinic grounding, or manual), review/edit it, and publish to any of WordPress / Telegram channel / bot users.

**Architecture:** Backend-first. `publishing/` holds isolated units (initData auth, AI generator, three publishers, an orchestration service). `miniapp/` serves a vanilla-JS form + an auth-gated JSON API. AI generation runs async on Django-Q (web search is slow); the Mini App polls for the draft. Every API call validates Telegram initData HMAC + a staff allowlist.

**Tech Stack:** Django 5.0.1, Python 3.13, SQLite, Django-Q2, OpenAI (Responses API + web_search tool), Telegram WebApp SDK, Django `TestCase`. Builds on Phase 1 (LLM/KB/queue) but is otherwise independent.

---

## Conventions
- Commands from `main/` with the venv (`.venv/bin/python`). Tests: `python manage.py test pages.tests.<module> -v 2`. Telegram/OpenAI/WordPress boundaries are mocked.
- Branch `updates`; per-task commits (pre-authorized). Every commit message ends with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Full suite is currently 96 tests, OK — keep it green.
- Spec: `docs/superpowers/specs/2026-06-04-miniapp-publishing-design.md`.

---

## Task 1: Config + `ContentDraft` model

**Files:**
- Modify: `main/pages/creditionals.py`, `main/.env.example`, `main/pages/models.py`, `main/pages/admin.py`
- Test: `main/pages/tests/test_publishing_config.py`

- [ ] **Step 1: Write the failing test**

`pages/tests/test_publishing_config.py`:

```python
from django.test import TestCase
from pages.models import BotUser, ContentDraft


class PublishingConfigTests(TestCase):
    def test_content_draft_defaults(self):
        u = BotUser.objects.create(name="Staff", user_id=1, user_name="s")
        d = ContentDraft.objects.create(created_by=u, kind="post", mode="ai", title="T")
        self.assertEqual(d.status, "draft")
        self.assertEqual(d.targets, {})
        self.assertEqual(d.publish_results, {})

    def test_config_symbols_exist(self):
        from pages import creditionals
        for name in ("WORDPRESS_URL", "WORDPRESS_USER", "WORDPRESS_APP_PASSWORD", "MINIAPP_URL"):
            self.assertTrue(hasattr(creditionals, name))
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python manage.py test pages.tests.test_publishing_config -v 2` → FAIL (`ContentDraft` import error).

- [ ] **Step 3: Add config to `pages/creditionals.py`**

Append:

```python
# --- Mini-App content publishing ---
WORDPRESS_URL = os.environ.get('WORDPRESS_URL', '')
WORDPRESS_USER = os.environ.get('WORDPRESS_USER', '')
WORDPRESS_APP_PASSWORD = os.environ.get('WORDPRESS_APP_PASSWORD', '')
MINIAPP_URL = os.environ.get('MINIAPP_URL', '')
```

Append to `main/.env.example`:

```bash
# --- Mini-App content publishing ---
WORDPRESS_URL=
WORDPRESS_USER=
WORDPRESS_APP_PASSWORD=
MINIAPP_URL=
```

- [ ] **Step 4: Add `ContentDraft` to `pages/models.py`**

```python
class ContentDraft(models.Model):
    KIND_CHOICES = [("post", "post"), ("article", "article")]
    MODE_CHOICES = [("ai", "ai"), ("manual", "manual")]
    STATUS_CHOICES = [
        ("draft", "draft"), ("generating", "generating"), ("ready", "ready"),
        ("published", "published"), ("failed", "failed"),
    ]
    created_by = models.ForeignKey(BotUser, null=True, blank=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default="post")
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="ai")
    title = models.CharField(max_length=512, blank=True)
    reference_link = models.URLField(blank=True)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="draft")
    error = models.TextField(blank=True)
    targets = models.JSONField(default=dict, blank=True)
    publish_results = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"[{self.status}] {self.kind}: {self.title}"
```

- [ ] **Step 5: Register read-mostly admin in `pages/admin.py`**

```python
from .models import ContentDraft


@admin.register(ContentDraft)
class ContentDraftAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "mode", "status", "created_by", "created_at")
    list_filter = ("status", "kind", "mode")
    search_fields = ("title", "body")
    readonly_fields = ("publish_results", "created_at", "updated_at")
```

- [ ] **Step 6: Migrate + test**

```bash
python manage.py makemigrations pages && python manage.py migrate
python manage.py test pages.tests.test_publishing_config -v 2   # PASS (2)
```

- [ ] **Step 7: Commit**

```bash
git add main/pages/creditionals.py main/.env.example main/pages/models.py main/pages/admin.py main/pages/migrations/
git commit -m "feat: publishing config + ContentDraft model"
```

---

## Task 2: Telegram initData auth (`publishing/auth.py`)

**Files:**
- Create: `main/pages/publishing/__init__.py`, `main/pages/publishing/auth.py`
- Test: `main/pages/tests/test_miniapp_auth.py`

**Fail-closed:** publishing is sensitive, so an empty allowlist denies everyone (unlike the support commands' back-compat).

- [ ] **Step 1: Create the package**

```bash
mkdir -p pages/publishing && touch pages/publishing/__init__.py
```

- [ ] **Step 2: Write the failing test**

`pages/tests/test_miniapp_auth.py`:

```python
import hmac, hashlib, json, time
from urllib.parse import urlencode
from unittest import mock
from django.test import SimpleTestCase
from pages.publishing.auth import validate_init_data, is_allowed

TOKEN = "12345:test-token"


def sign(params, token=TOKEN):
    dcs = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode({**params, "hash": h})


def base_params():
    return {"auth_date": str(int(time.time())),
            "user": json.dumps({"id": 777, "first_name": "S"})}


class InitDataAuthTests(SimpleTestCase):
    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    def test_valid_init_data_returns_user(self):
        user = validate_init_data(sign(base_params()))
        self.assertEqual(user["id"], 777)

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    def test_tampered_hash_rejected(self):
        raw = sign(base_params())
        self.assertIsNone(validate_init_data(raw + "0"))  # corrupt the hash tail

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    def test_stale_auth_date_rejected(self):
        params = {"auth_date": "1", "user": json.dumps({"id": 1})}
        self.assertIsNone(validate_init_data(sign(params)))

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    def test_wrong_token_rejected(self):
        raw = sign(base_params(), token="99:other")
        self.assertIsNone(validate_init_data(raw))

    @mock.patch("pages.creditionals.ADMIN_USER_IDS", [777])
    def test_is_allowed_respects_allowlist(self):
        self.assertTrue(is_allowed({"id": 777}))
        self.assertFalse(is_allowed({"id": 1}))

    @mock.patch("pages.creditionals.ADMIN_USER_IDS", [])
    def test_is_allowed_fails_closed_when_empty(self):
        self.assertFalse(is_allowed({"id": 777}))
```

- [ ] **Step 3: Run it and watch it fail**

Run: `python manage.py test pages.tests.test_miniapp_auth -v 2` → FAIL (module missing).

- [ ] **Step 4: Write `publishing/auth.py`**

```python
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


def validate_init_data(raw_init_data, max_age_seconds=86400):
    """Return the Telegram user dict if initData HMAC is valid + fresh, else None."""
    from ..creditionals import BOT_TOKEN
    if not raw_init_data:
        return None
    pairs = dict(parse_qsl(raw_init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    if max_age_seconds and (time.time() - auth_date) > max_age_seconds:
        return None
    try:
        return json.loads(pairs.get("user", ""))
    except (json.JSONDecodeError, TypeError):
        return None


def is_allowed(user):
    """Fail-closed staff gate: empty allowlist denies everyone."""
    from ..creditionals import ADMIN_USER_IDS
    return bool(user) and bool(ADMIN_USER_IDS) and user.get("id") in ADMIN_USER_IDS
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python manage.py test pages.tests.test_miniapp_auth -v 2` → PASS (6).

- [ ] **Step 6: Commit**

```bash
git add main/pages/publishing/__init__.py main/pages/publishing/auth.py main/pages/tests/test_miniapp_auth.py
git commit -m "feat: Telegram Mini App initData HMAC validation + staff allowlist"
```

---

## Task 3: Publishers (`publishing/publishers.py`)

**Files:**
- Create: `main/pages/publishing/publishers.py`
- Test: `main/pages/tests/test_publishers.py`

- [ ] **Step 1: Write the failing test**

`pages/tests/test_publishers.py`:

```python
from unittest import mock
from django.test import TestCase
from pages.models import BotUser, ChannelBot, ContentDraft
from pages.publishing import publishers


def make_draft():
    u = BotUser.objects.create(name="S", user_id=1, user_name="s")
    return ContentDraft.objects.create(created_by=u, kind="post", title="Salom", body="Tana matni")


class WordPressPublisherTests(TestCase):
    @mock.patch("pages.publishing.publishers.requests.post")
    def test_publish_success_returns_url(self, post):
        post.return_value.status_code = 201
        post.return_value.json.return_value = {"link": "https://clinic/x", "id": 5}
        with mock.patch("pages.creditionals.WORDPRESS_URL", "https://clinic"), \
             mock.patch("pages.creditionals.WORDPRESS_USER", "u"), \
             mock.patch("pages.creditionals.WORDPRESS_APP_PASSWORD", "p"):
            res = publishers.WordPressPublisher().publish(make_draft())
        self.assertTrue(res["ok"])
        self.assertEqual(res["url"], "https://clinic/x")
        self.assertTrue(post.call_args.args[0].endswith("/wp-json/wp/v2/posts"))

    @mock.patch("pages.publishing.publishers.requests.post")
    def test_publish_failure_returns_error(self, post):
        post.return_value.status_code = 401
        post.return_value.json.return_value = {"message": "bad auth"}
        res = publishers.WordPressPublisher().publish(make_draft())
        self.assertFalse(res["ok"])
        self.assertIn("bad auth", res["error"])


class ChannelPublisherTests(TestCase):
    @mock.patch("pages.publishing.publishers.sentMessage")
    def test_no_channel_registered(self, sent):
        res = publishers.ChannelPublisher().publish(make_draft())
        self.assertFalse(res["ok"])
        sent.assert_not_called()

    @mock.patch("pages.publishing.publishers.sentMessage",
                return_value={"ok": True, "result": {"message_id": 9}})
    def test_publish_to_channel(self, sent):
        ChannelBot.objects.create(name="C", chat_id=-100)
        res = publishers.ChannelPublisher().publish(make_draft())
        self.assertTrue(res["ok"])
        self.assertEqual(res["message_id"], 9)


class BotUsersPublisherTests(TestCase):
    @mock.patch("pages.publishing.publishers.sentMessage", return_value={"ok": True})
    def test_broadcast_counts(self, sent):
        BotUser.objects.create(name="A", user_id=10, user_name="a")
        BotUser.objects.create(name="B", user_id=11, user_name="b")
        res = publishers.BotUsersPublisher().publish(make_draft())
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], sent.call_count)
        self.assertGreaterEqual(res["count"], 2)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python manage.py test pages.tests.test_publishers -v 2` → FAIL (module missing).

- [ ] **Step 3: Write `publishing/publishers.py`**

```python
import base64

import requests

from ..TelegramAPI import sentMessage
from ..models import BotUser, ChannelBot


def _telegram_text(draft):
    return f"<b>{draft.title}</b>\n\n{draft.body}" if draft.title else draft.body


class WordPressPublisher:
    def publish(self, draft):
        from ..creditionals import WORDPRESS_URL, WORDPRESS_USER, WORDPRESS_APP_PASSWORD
        url = WORDPRESS_URL.rstrip("/") + "/wp-json/wp/v2/posts"
        token = base64.b64encode(
            f"{WORDPRESS_USER}:{WORDPRESS_APP_PASSWORD}".encode()
        ).decode()
        try:
            resp = requests.post(
                url,
                headers={"Authorization": f"Basic {token}"},
                json={"title": draft.title, "content": draft.body, "status": "publish"},
                timeout=30,
            )
            data = resp.json()
            if resp.status_code in (200, 201) and "link" in data:
                return {"ok": True, "url": data["link"]}
            return {"ok": False, "error": data.get("message", f"HTTP {resp.status_code}")}
        except Exception as exc:  # network/parse errors must not crash publishing
            return {"ok": False, "error": str(exc)}


class ChannelPublisher:
    def publish(self, draft):
        channel = ChannelBot.objects.first()
        if not channel:
            return {"ok": False, "error": "no channel registered"}
        res = sentMessage("Message", channel.chat_id, _telegram_text(draft))
        if isinstance(res, dict) and res.get("ok"):
            return {"ok": True, "message_id": res["result"]["message_id"]}
        return {"ok": False, "error": (res or {}).get("description", "send failed")}


class BotUsersPublisher:
    def publish(self, draft):
        text = _telegram_text(draft)
        count = 0
        for user in BotUser.objects.all():
            res = sentMessage("Message", user.user_id, text)
            if isinstance(res, dict) and res.get("ok"):
                count += 1
        return {"ok": True, "count": count}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python manage.py test pages.tests.test_publishers -v 2` → PASS (5).

- [ ] **Step 5: Commit**

```bash
git add main/pages/publishing/publishers.py main/pages/tests/test_publishers.py
git commit -m "feat: WordPress / channel / bot-users publishers"
```

---

## Task 4: AI generator (`publishing/generator.py`)

**Files:**
- Create: `main/pages/publishing/generator.py`
- Test: `main/pages/tests/test_generator.py`

The OpenAI web-search call is isolated here and mocked in tests. **Verify the exact tool name/SDK
call against current OpenAI docs at build time** (it's the one external unknown).

- [ ] **Step 1: Write the failing test**

`pages/tests/test_generator.py`:

```python
from unittest import mock
from django.test import SimpleTestCase
from pages.publishing import generator


class GeneratorTests(SimpleTestCase):
    @mock.patch("pages.publishing.generator._openai_web_search")
    def test_builds_prompt_and_returns_body(self, search):
        search.return_value = "Yaratilgan maqola matni"
        out = generator.generate_content(
            kind="article", title="Kardiologiya", reference_link="https://x/y",
            kb_snapshot="KB_MARKER",
        )
        self.assertEqual(out["title"], "Kardiologiya")
        self.assertEqual(out["body"], "Yaratilgan maqola matni")
        prompt = search.call_args.args[0]
        self.assertIn("Kardiologiya", prompt)
        self.assertIn("KB_MARKER", prompt)
        self.assertIn("https://x/y", prompt)

    @mock.patch("pages.publishing.generator._openai_web_search")
    def test_post_kind_uses_short_style(self, search):
        search.return_value = "qisqa post"
        generator.generate_content(kind="post", title="Aksiya", reference_link="", kb_snapshot="")
        self.assertIn("post", search.call_args.args[0].lower())
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python manage.py test pages.tests.test_generator -v 2` → FAIL (module missing).

- [ ] **Step 3: Write `publishing/generator.py`**

```python
def _build_prompt(kind, title, reference_link, kb_snapshot):
    style = (
        "qisqa, kanal uchun jozibali post (bir necha jumla, harakatga chaqiruv bilan)"
        if kind == "post"
        else "uzun, tuzilgan maqola (sarlavhalar va bo'limlar bilan)"
    )
    ref = f"Ushbu havoladagi maqolani ham o'qib, hisobga ol: {reference_link}\n" if reference_link else ""
    return (
        f"Sen klinikaning kontent-muharririsan. Klinika uchun {style} yoz.\n"
        f"Mavzu: {title}\n"
        f"{ref}"
        f"Internetdan ishonchli manbalarni qidir va shularga tayan.\n"
        f"Matnni klinikaga moslab yoz. Klinika ma'lumoti:\n{kb_snapshot}\n"
        f"O'zbek tilida yoz. Faqat tayyor kontent matnini qaytar (izohsiz)."
    )


def _openai_web_search(prompt, model="gpt-4o"):
    """Isolated OpenAI web-search call. Mocked in tests. Verify tool name vs current SDK."""
    from openai import OpenAI
    from ..creditionals import OPENAI_API_KEY
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.responses.create(
        model=model,
        tools=[{"type": "web_search"}],
        input=prompt,
    )
    return resp.output_text


def generate_content(kind, title, reference_link="", kb_snapshot="", model="gpt-4o"):
    prompt = _build_prompt(kind, title, reference_link, kb_snapshot)
    body = _openai_web_search(prompt, model=model)
    return {"title": title, "body": body}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python manage.py test pages.tests.test_generator -v 2` → PASS (2).

- [ ] **Step 5: Commit**

```bash
git add main/pages/publishing/generator.py main/pages/tests/test_generator.py
git commit -m "feat: AI content generator (OpenAI web search + clinic grounding)"
```

---

## Task 5: Orchestration service + async job

**Files:**
- Create: `main/pages/publishing/service.py`
- Modify: `main/pages/tasks.py`
- Test: `main/pages/tests/test_publishing_service.py`

- [ ] **Step 1: Write the failing test**

`pages/tests/test_publishing_service.py`:

```python
from unittest import mock
from django.test import TestCase
from pages.models import BotUser, ContentDraft
from pages.publishing import service


class ServiceTests(TestCase):
    def setUp(self):
        self.user = BotUser.objects.create(name="S", user_id=1, user_name="s")

    @mock.patch("django_q.tasks.async_task")
    def test_start_generation_creates_draft_and_enqueues(self, async_task):
        draft = service.start_generation(self.user, "post", "Aksiya", "https://x")
        self.assertEqual(draft.status, "generating")
        self.assertEqual(draft.mode, "ai")
        async_task.assert_called_once_with("pages.tasks.generate_content_job", draft.id)

    @mock.patch("pages.publishing.generator.generate_content",
                return_value={"title": "T", "body": "Tayyor matn"})
    def test_run_generation_fills_body_and_marks_ready(self, gen):
        draft = ContentDraft.objects.create(created_by=self.user, kind="post",
                                            title="T", status="generating")
        service.run_generation(draft.id)
        draft.refresh_from_db()
        self.assertEqual(draft.status, "ready")
        self.assertEqual(draft.body, "Tayyor matn")

    @mock.patch("pages.publishing.generator.generate_content", side_effect=RuntimeError("boom"))
    def test_run_generation_marks_failed_on_error(self, gen):
        draft = ContentDraft.objects.create(created_by=self.user, kind="post",
                                            title="T", status="generating")
        service.run_generation(draft.id)
        draft.refresh_from_db()
        self.assertEqual(draft.status, "failed")
        self.assertIn("boom", draft.error)

    def test_publish_draft_records_per_target_results(self):
        draft = ContentDraft.objects.create(created_by=self.user, kind="post", title="T", body="B")

        class OK:
            def publish(self, d):
                return {"ok": True, "url": "https://x"}

        class Bad:
            def publish(self, d):
                return {"ok": False, "error": "no"}

        with mock.patch.dict(service.PUBLISHERS, {"site": OK, "channel": Bad}, clear=True):
            results = service.publish_draft(draft, {"site": True, "channel": True})
        self.assertEqual(results["site"]["url"], "https://x")
        self.assertFalse(results["channel"]["ok"])
        draft.refresh_from_db()
        self.assertEqual(draft.status, "published")  # any target ok → published
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python manage.py test pages.tests.test_publishing_service -v 2` → FAIL (module missing).

- [ ] **Step 3: Write `publishing/service.py`**

```python
from ..models import ContentDraft
from .publishers import WordPressPublisher, ChannelPublisher, BotUsersPublisher

PUBLISHERS = {
    "site": WordPressPublisher,
    "channel": ChannelPublisher,
    "bot_users": BotUsersPublisher,
}


def start_generation(created_by, kind, title, reference_link=""):
    draft = ContentDraft.objects.create(
        created_by=created_by, kind=kind, mode="ai", title=title,
        reference_link=reference_link or "", status="generating",
    )
    from django_q.tasks import async_task
    async_task("pages.tasks.generate_content_job", draft.id)
    return draft


def run_generation(draft_id):
    from ..knowledge.snapshot import get_kb_snapshot
    from .generator import generate_content
    try:
        draft = ContentDraft.objects.get(id=draft_id)
    except ContentDraft.DoesNotExist:
        return
    try:
        result = generate_content(draft.kind, draft.title, draft.reference_link, get_kb_snapshot())
        draft.body = result["body"]
        draft.status = "ready"
        draft.save(update_fields=["body", "status", "updated_at"])
    except Exception as exc:
        draft.status = "failed"
        draft.error = str(exc)
        draft.save(update_fields=["status", "error", "updated_at"])


def publish_draft(draft, targets):
    results = {}
    any_ok = False
    for key, want in (targets or {}).items():
        if not want or key not in PUBLISHERS:
            continue
        res = PUBLISHERS[key]().publish(draft)
        results[key] = res
        any_ok = any_ok or bool(res.get("ok"))
    draft.targets = targets or {}
    draft.publish_results = results
    draft.status = "published" if any_ok else "failed"
    draft.save(update_fields=["targets", "publish_results", "status", "updated_at"])
    return results
```

- [ ] **Step 4: Add the job to `pages/tasks.py`**

Append:

```python
def generate_content_job(draft_id):
    """Django-Q job: run async AI generation for a content draft."""
    from .publishing.service import run_generation
    run_generation(draft_id)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python manage.py test pages.tests.test_publishing_service -v 2` → PASS (4).

- [ ] **Step 6: Commit**

```bash
git add main/pages/publishing/service.py main/pages/tasks.py main/pages/tests/test_publishing_service.py
git commit -m "feat: publishing orchestration service + async generation job"
```

---

## Task 6: Mini App JSON API (`miniapp/views.py` + URLs)

**Files:**
- Create: `main/pages/miniapp/__init__.py`, `main/pages/miniapp/views.py`
- Modify: `main/pages/urls.py`
- Test: `main/pages/tests/test_miniapp_api.py`

- [ ] **Step 1: Create the package**

```bash
mkdir -p pages/miniapp && touch pages/miniapp/__init__.py
```

- [ ] **Step 2: Write the failing test**

`pages/tests/test_miniapp_api.py`:

```python
import hmac, hashlib, json, time
from urllib.parse import urlencode
from unittest import mock
from django.test import TestCase, Client

TOKEN = "12345:test-token"


def sign(params, token=TOKEN):
    dcs = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode({**params, "hash": h})


def valid_init(uid=777):
    return sign({"auth_date": str(int(time.time())),
                 "user": json.dumps({"id": uid, "first_name": "S"})})


class MiniAppApiTests(TestCase):
    def setUp(self):
        self.c = Client()

    def test_generate_forbidden_without_initdata(self):
        r = self.c.post("/miniapp/api/generate", data="{}", content_type="application/json")
        self.assertEqual(r.status_code, 403)

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    @mock.patch("pages.creditionals.ADMIN_USER_IDS", [777])
    @mock.patch("pages.miniapp.views.start_generation")
    def test_generate_authed_enqueues(self, start):
        start.return_value = mock.Mock(id=9, status="generating")
        r = self.c.post("/miniapp/api/generate",
                        data=json.dumps({"kind": "post", "title": "T"}),
                        content_type="application/json",
                        HTTP_X_TELEGRAM_INIT_DATA=valid_init())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["draft_id"], 9)
        start.assert_called_once()

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    @mock.patch("pages.creditionals.ADMIN_USER_IDS", [777])
    @mock.patch("pages.miniapp.views.publish_draft", return_value={"channel": {"ok": True}})
    def test_publish_manual_creates_draft_and_publishes(self, pub):
        r = self.c.post("/miniapp/api/publish",
                        data=json.dumps({"kind": "post", "title": "T", "body": "B",
                                         "targets": {"channel": True}}),
                        content_type="application/json",
                        HTTP_X_TELEGRAM_INIT_DATA=valid_init())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["results"]["channel"]["ok"])
        pub.assert_called_once()

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    @mock.patch("pages.creditionals.ADMIN_USER_IDS", [42])  # 777 not allowed
    def test_non_allowlisted_forbidden(self):
        r = self.c.post("/miniapp/api/generate", data=json.dumps({"kind": "post", "title": "T"}),
                        content_type="application/json", HTTP_X_TELEGRAM_INIT_DATA=valid_init(777))
        self.assertEqual(r.status_code, 403)
```

- [ ] **Step 3: Run it and watch it fail**

Run: `python manage.py test pages.tests.test_miniapp_api -v 2` → FAIL (routes missing).

- [ ] **Step 4: Write `miniapp/views.py`**

```python
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from ..publishing.auth import validate_init_data, is_allowed
from ..publishing.service import start_generation, publish_draft
from ..models import BotUser, ContentDraft


def _staff(request):
    """Validate initData + allowlist; return (or create) the staff BotUser, else None."""
    user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""))
    if not user or not is_allowed(user):
        return None
    botuser, _ = BotUser.objects.get_or_create(
        user_id=user["id"],
        defaults={"name": user.get("first_name", ""), "user_name": user.get("username", "")},
    )
    return botuser


def composer(request):
    """Serve the Mini App shell (public HTML; all actions are auth-gated via the API)."""
    return render(request, "miniapp/composer.html", {})


@csrf_exempt
def api_generate(request):
    staff = _staff(request)
    if not staff:
        return JsonResponse({"error": "forbidden"}, status=403)
    data = json.loads(request.body or "{}")
    draft = start_generation(staff, data.get("kind", "post"), data.get("title", ""),
                             data.get("reference_link", ""))
    return JsonResponse({"draft_id": draft.id, "status": draft.status})


@csrf_exempt
def api_draft(request, draft_id):
    staff = _staff(request)
    if not staff:
        return JsonResponse({"error": "forbidden"}, status=403)
    try:
        draft = ContentDraft.objects.get(id=draft_id)
    except ContentDraft.DoesNotExist:
        return JsonResponse({"error": "not found"}, status=404)
    return JsonResponse({"status": draft.status, "body": draft.body, "error": draft.error})


@csrf_exempt
def api_publish(request):
    staff = _staff(request)
    if not staff:
        return JsonResponse({"error": "forbidden"}, status=403)
    data = json.loads(request.body or "{}")
    draft_id = data.get("draft_id")
    if draft_id:
        try:
            draft = ContentDraft.objects.get(id=draft_id)
        except ContentDraft.DoesNotExist:
            return JsonResponse({"error": "not found"}, status=404)
        draft.title = data.get("title", draft.title)
        draft.body = data.get("body", draft.body)
        draft.save(update_fields=["title", "body", "updated_at"])
    else:
        draft = ContentDraft.objects.create(
            created_by=staff, kind=data.get("kind", "post"), mode="manual",
            title=data.get("title", ""), body=data.get("body", ""), status="draft",
        )
    results = publish_draft(draft, data.get("targets", {}))
    return JsonResponse({"status": draft.status, "results": results})
```

- [ ] **Step 5: Wire URLs in `pages/urls.py`**

Add the imports and routes:

```python
from .miniapp.views import composer, api_generate, api_draft, api_publish
```
```python
    path('miniapp/', composer),
    path('miniapp/api/generate', api_generate),
    path('miniapp/api/draft/<int:draft_id>', api_draft),
    path('miniapp/api/publish', api_publish),
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python manage.py test pages.tests.test_miniapp_api -v 2` → PASS (4).

- [ ] **Step 7: Commit**

```bash
git add main/pages/miniapp/__init__.py main/pages/miniapp/views.py main/pages/urls.py main/pages/tests/test_miniapp_api.py
git commit -m "feat: Mini App auth-gated JSON API (generate/draft/publish)"
```

---

## Task 7: Mini App page + bot launch button

**Files:**
- Create: `main/pages/templates/miniapp/composer.html`
- Modify: `main/pages/views.py` (add the `web_app` button to the admin keyboard)
- Test: `main/pages/tests/test_miniapp_page.py`

(Template lives under `pages/templates/` so Django's `APP_DIRS` loader finds it.)

- [ ] **Step 1: Write the failing test**

`pages/tests/test_miniapp_page.py`:

```python
from django.test import TestCase, Client


class MiniAppPageTests(TestCase):
    def test_composer_page_renders_form(self):
        r = Client().get("/miniapp/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "telegram-web-app.js")
        self.assertContains(r, 'id="title"')
        self.assertContains(r, 'id="body"')
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python manage.py test pages.tests.test_miniapp_page -v 2` → FAIL (template missing).

- [ ] **Step 3: Create `main/pages/templates/miniapp/composer.html`**

```html
<!doctype html>
<html lang="uz">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kontent</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    body{font-family:system-ui,sans-serif;margin:0;padding:16px;background:var(--tg-theme-bg-color,#fff);color:var(--tg-theme-text-color,#000)}
    label{display:block;margin:10px 0 4px;font-weight:600}
    input,textarea,select{width:100%;box-sizing:border-box;padding:8px;font-size:15px}
    textarea{min-height:160px}
    .row{margin:8px 0}.targets label{display:inline-flex;align-items:center;font-weight:400;margin-right:14px}
    .targets input{width:auto;margin-right:6px}
    button{margin-top:14px;padding:11px;width:100%;font-size:16px;border:0;border-radius:8px;background:var(--tg-theme-button-color,#2481cc);color:var(--tg-theme-button-text-color,#fff)}
    #status{margin-top:10px;font-size:14px;opacity:.8}
    .hidden{display:none}
  </style>
</head>
<body>
  <div class="row">
    <label>Tur</label>
    <select id="kind"><option value="post">Post (qisqa)</option><option value="article">Maqola (uzun)</option></select>
  </div>
  <div class="row">
    <label>Usul</label>
    <select id="mode"><option value="ai">AI yozadi</option><option value="manual">O'zim yozaman</option></select>
  </div>
  <div class="row"><label for="title">Sarlavha</label><input id="title" type="text"></div>
  <div class="row" id="refRow"><label for="ref">Manba havola (ixtiyoriy)</label><input id="ref" type="url"></div>
  <button id="genBtn">AI bilan yozdirish</button>
  <div class="row"><label for="body">Matn</label><textarea id="body"></textarea></div>
  <div class="row targets">
    <label>Qayerga:</label>
    <label><input type="checkbox" id="t_site">Sayt</label>
    <label><input type="checkbox" id="t_channel">Kanal</label>
    <label><input type="checkbox" id="t_users">Bot foydalanuvchilari</label>
  </div>
  <button id="pubBtn">Publish</button>
  <div id="status"></div>

<script>
const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) tg.ready();
const initData = tg ? tg.initData : "";
const $ = id => document.getElementById(id);
let draftId = null;
const setStatus = m => $("status").textContent = m;

function api(path, method, body){
  return fetch(path, {method, headers:{"Content-Type":"application/json","X-Telegram-Init-Data":initData},
    body: body ? JSON.stringify(body) : undefined}).then(r => r.json().then(j => ({ok:r.ok, j})));
}
function syncMode(){
  const ai = $("mode").value === "ai";
  $("genBtn").classList.toggle("hidden", !ai);
  $("refRow").classList.toggle("hidden", !ai);
}
$("mode").addEventListener("change", syncMode); syncMode();

$("genBtn").addEventListener("click", async () => {
  setStatus("Yozilmoqda…"); $("genBtn").disabled = true;
  const {ok, j} = await api("/miniapp/api/generate","POST",
    {kind:$("kind").value, title:$("title").value, reference_link:$("ref").value});
  if(!ok){ setStatus("Xatolik: "+(j.error||"")); $("genBtn").disabled=false; return; }
  draftId = j.draft_id;
  const poll = setInterval(async () => {
    const {j:d} = await api("/miniapp/api/draft/"+draftId,"GET");
    if(d.status === "ready"){ clearInterval(poll); $("body").value = d.body; setStatus("Tayyor — tahrirlang."); $("genBtn").disabled=false; }
    else if(d.status === "failed"){ clearInterval(poll); setStatus("Yaratishda xato: "+(d.error||"")); $("genBtn").disabled=false; }
  }, 2000);
});

$("pubBtn").addEventListener("click", async () => {
  setStatus("Yuborilmoqda…"); $("pubBtn").disabled = true;
  const {ok, j} = await api("/miniapp/api/publish","POST",{
    draft_id:draftId, kind:$("kind").value, title:$("title").value, body:$("body").value,
    targets:{site:$("t_site").checked, channel:$("t_channel").checked, bot_users:$("t_users").checked}});
  $("pubBtn").disabled = false;
  if(!ok){ setStatus("Xatolik: "+(j.error||"")); return; }
  setStatus("Natija: "+JSON.stringify(j.results));
});
</script>
</body>
</html>
```

- [ ] **Step 4: Add the launch button to the admin keyboard in `pages/views.py`**

In the `/getadmin` success branch where the admin reply-keyboard is built, add the import and a
`web_app` button row (guarded so it's only shown when `MINIAPP_URL` is configured — Telegram rejects
an empty `web_app` url). After building `reply_markup`'s keyboard, insert:

```python
                            from .creditionals import MINIAPP_URL
                            if MINIAPP_URL:
                                reply_markup['keyboard'].append(
                                    [{'text': "✍️ Kontent", 'web_app': {'url': MINIAPP_URL}}]
                                )
```

(Place it immediately after the `reply_markup = {...}` assignment and before the `sendMessage`/`requests.post` that sends the keyboard.)

- [ ] **Step 5: Run the page test + full suite**

```bash
python manage.py test pages.tests.test_miniapp_page -v 2     # PASS (1)
python manage.py test pages -v 1                              # ALL pass (twice, deterministic)
```

- [ ] **Step 6: Commit**

```bash
git add main/pages/templates/miniapp/composer.html main/pages/views.py main/pages/tests/test_miniapp_page.py
git commit -m "feat: Mini App composer page + bot launch button"
```

---

## Self-review checklist (run after Task 7)
- Spec coverage: auth, generator, three publishers, service, API, page, launch button — all present.
- initData validation is on every API endpoint; `is_allowed` fails closed.
- No WordPress creds ever returned to the frontend.
- Generation is async (job) + polled; publish records per-target results.

## Manual verification (live, before relying on it)
Set `WORDPRESS_URL/USER/APP_PASSWORD`, `MINIAPP_URL` (HTTPS), ensure `qcluster` runs, re-register the
webhook. As an allowlisted admin: open the bot, tap **✍️ Kontent**, generate an AI post, edit it,
publish to the channel, and confirm it arrives; then try a WordPress article and confirm the post URL.

## Out of scope / future
- WP-draft (second review tier), scheduling, images/WYSIWYG, analytics (spec §12).

