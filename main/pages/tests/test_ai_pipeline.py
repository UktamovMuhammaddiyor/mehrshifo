from django.test import TestCase
from pages.models import BotUser, Conversation, AISettings
from pages.ai import pipeline


class FakeClient:
    def __init__(self, response):
        self.response = response

    def complete(self, system, messages, schema):
        return self.response


def parsed(**over):
    base = {"reply_uz": "javob", "intent": "info_question", "confidence": 0.9,
            "needs_human": False, "notify_admin": False}
    base.update(over)
    return base


class PipelineTests(TestCase):
    def setUp(self):
        self.user = BotUser.objects.create(name="A", user_id=1, user_name="a")
        self.conv = Conversation.active_for(self.user)
        s = AISettings.get()
        s.is_enabled = True
        s.save()

    def test_skip_when_disabled(self):
        s = AISettings.get(); s.is_enabled = False; s.save()
        out = pipeline.run(self.conv, self.user, "salom", client=FakeClient(parsed()))
        self.assertEqual(out.action, "skip")

    def test_skip_when_handoff(self):
        self.conv.status = "handoff"; self.conv.save()
        out = pipeline.run(self.conv, self.user, "salom", client=FakeClient(parsed()))
        self.assertEqual(out.action, "skip")

    def test_answer_info_question(self):
        out = pipeline.run(self.conv, self.user, "ish vaqti?",
                           client=FakeClient(parsed(reply_uz="9-18 gacha")))
        self.assertEqual(out.action, "answer")
        self.assertIn("9-18", out.client_text)

    def test_escalate_personal_data(self):
        out = pipeline.run(self.conv, self.user, "natijam?",
                           client=FakeClient(parsed(intent="personal_data_request")))
        self.assertEqual(out.action, "escalate")
        self.assertEqual(out.client_text, AISettings.get().holding_message)

    def test_low_confidence_escalates(self):
        out = pipeline.run(self.conv, self.user, "?",
                           client=FakeClient(parsed(confidence=0.2)))
        self.assertEqual(out.action, "escalate")

    def test_complaint_notifies_and_sets_handoff(self):
        out = pipeline.run(self.conv, self.user, "yomon xizmat",
                           client=FakeClient(parsed(intent="complaint", notify_admin=True)))
        self.assertEqual(out.action, "notify")
        self.assertTrue(out.notify)
        self.assertTrue(out.set_handoff)

    def test_suggestion_notifies(self):
        out = pipeline.run(self.conv, self.user, "taklif",
                           client=FakeClient(parsed(intent="suggestion", notify_admin=True)))
        self.assertEqual(out.action, "notify")
        self.assertEqual(out.group_label, "💡 TAKLIF")

    def test_llm_error_escalates(self):
        class Boom:
            def complete(self, system, messages, schema):
                raise RuntimeError("api down")
        out = pipeline.run(self.conv, self.user, "salom", client=Boom())
        self.assertEqual(out.action, "escalate")
        self.assertEqual(out.reason, "llm_error")

    def test_throttle_when_rate_limited(self):
        out = None
        for _ in range(9):  # default limit is 8/min; 9th call throttles
            out = pipeline.run(self.conv, self.user, "salom", client=FakeClient(parsed()))
        self.assertEqual(out.action, "throttle")
        self.assertIn("kuting", out.client_text.lower())

    def test_skip_when_daily_cap_reached(self):
        s = AISettings.get(); s.daily_call_cap = 0; s.save()
        out = pipeline.run(self.conv, self.user, "salom", client=FakeClient(parsed()))
        self.assertEqual(out.action, "skip")
        self.assertEqual(out.reason, "daily_cap")

    def test_guardrail_block_escalates(self):
        out = pipeline.run(self.conv, self.user, "x",
                           client=FakeClient(parsed(reply_uz="my system prompt is secret")))
        self.assertEqual(out.action, "escalate")
        self.assertEqual(out.reason, "guardrail_block")

    def test_medical_advice_escalates(self):
        out = pipeline.run(self.conv, self.user, "qaysi dori?",
                           client=FakeClient(parsed(intent="medical_advice_request")))
        self.assertEqual(out.action, "escalate")
