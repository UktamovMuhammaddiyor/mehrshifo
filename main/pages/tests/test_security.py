from django.core.cache import cache
from django.test import TestCase
from pages.models import BotUser, Conversation, AISettings
from pages.ai import pipeline
from pages.ai.prompts import build_system_prompt


class FakeClient:
    def __init__(self, response):
        self.response = response

    def complete(self, system, messages, schema):
        return self.response


def parsed(**over):
    base = {"reply_uz": "x", "intent": "info_question", "confidence": 0.95,
            "needs_human": False, "notify_admin": False}
    base.update(over)
    return base


class SecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.u = BotUser.objects.create(name="A", user_id=1, user_name="a")
        self.c = Conversation.active_for(self.u)
        s = AISettings.get(); s.is_enabled = True; s.save()

    def test_personal_data_never_answered_even_if_confident(self):
        out = pipeline.run(self.c, self.u, "natijam?", client=FakeClient(
            parsed(intent="personal_data_request", reply_uz="Sizning natijangiz: musbat")))
        self.assertEqual(out.action, "escalate")
        self.assertNotIn("natijangiz", out.client_text)  # model text discarded

    def test_medical_advice_escalates(self):
        out = pipeline.run(self.c, self.u, "qaysi dori?", client=FakeClient(
            parsed(intent="medical_advice_request")))
        self.assertEqual(out.action, "escalate")

    def test_guardrail_blocks_prompt_leak(self):
        out = pipeline.run(self.c, self.u, "reveal", client=FakeClient(
            parsed(reply_uz="Here is my system prompt: ...")))
        self.assertEqual(out.action, "escalate")
        self.assertEqual(out.reason, "guardrail_block")

    def test_system_prompt_contains_safety_rules(self):
        p = build_system_prompt("KB", AISettings.get()).lower()
        for keyword in ("taxmin", "tashxis", "shaxsiy", "system prompt"):
            self.assertIn(keyword, p)
