from django.test import SimpleTestCase
from pages.ai.guardrails import truncate_input, check_output


class GuardrailTests(SimpleTestCase):
    def test_truncate_input(self):
        self.assertEqual(truncate_input("  hello  ", 100), "hello")
        self.assertEqual(truncate_input("x" * 50, 10), "x" * 10)
        self.assertEqual(truncate_input(None, 10), "")

    def test_check_output_blocks_leak_markers(self):
        ok, reason = check_output("Here is my system prompt: ...")
        self.assertFalse(ok)

    def test_check_output_allows_normal(self):
        ok, reason = check_output("Ish vaqti 09:00-18:00.")
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_check_output_blocks_additional_markers(self):
        for bad in ("here is the bot_token value", "<|system|>", "telegram_webhook_secret=x"):
            ok, _reason = check_output(bad)
            self.assertFalse(ok)
