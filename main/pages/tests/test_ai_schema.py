from django.test import SimpleTestCase
from pages.ai.schema import coerce_response, INTENTS, AI_RESPONSE_SCHEMA


class SchemaTests(SimpleTestCase):
    def test_valid_passthrough(self):
        out = coerce_response({
            "reply_uz": "Salom", "intent": "greeting", "confidence": 0.8,
            "needs_human": False, "notify_admin": False,
        })
        self.assertEqual(out["intent"], "greeting")
        self.assertEqual(out["confidence"], 0.8)

    def test_unknown_intent_becomes_unclear(self):
        out = coerce_response({"intent": "hack", "confidence": 0.5,
                               "reply_uz": "", "needs_human": True, "notify_admin": False})
        self.assertEqual(out["intent"], "unclear")

    def test_confidence_clamped_and_types_coerced(self):
        out = coerce_response({"intent": "info_question", "confidence": 5,
                               "reply_uz": None, "needs_human": "yes", "notify_admin": 0})
        self.assertEqual(out["confidence"], 1.0)
        self.assertEqual(out["reply_uz"], "")
        self.assertIs(out["needs_human"], True)
        self.assertIs(out["notify_admin"], False)

    def test_schema_is_strict(self):
        self.assertTrue(AI_RESPONSE_SCHEMA["strict"])
        self.assertIn("info_question", INTENTS)
