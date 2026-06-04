from unittest import mock
from django.test import SimpleTestCase
from pages.ai.client import OpenAIClient
from pages.ai.schema import AI_RESPONSE_SCHEMA


def _fake_completion(content):
    msg = mock.Mock()
    msg.content = content
    choice = mock.Mock()
    choice.message = msg
    resp = mock.Mock()
    resp.choices = [choice]
    return resp


class OpenAIClientTests(SimpleTestCase):
    @mock.patch("openai.OpenAI")
    def test_complete_parses_structured_output(self, MockOpenAI):
        MockOpenAI.return_value.chat.completions.create.return_value = _fake_completion(
            '{"reply_uz":"Salom","intent":"greeting","confidence":0.9,'
            '"needs_human":false,"notify_admin":false}'
        )
        c = OpenAIClient(model="gpt-4o")
        out = c.complete("sys", [{"role": "user", "content": "salom"}], AI_RESPONSE_SCHEMA)
        self.assertEqual(out["intent"], "greeting")
        self.assertEqual(out["reply_uz"], "Salom")
        self.assertFalse(out["needs_human"])

    @mock.patch("openai.OpenAI")
    def test_request_includes_system_and_messages(self, MockOpenAI):
        create = MockOpenAI.return_value.chat.completions.create
        create.return_value = _fake_completion(
            '{"reply_uz":"x","intent":"unclear","confidence":0.1,'
            '"needs_human":true,"notify_admin":false}'
        )
        OpenAIClient(model="gpt-4o").complete(
            "SYSTEM", [{"role": "user", "content": "hi"}], AI_RESPONSE_SCHEMA
        )
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["messages"][0], {"role": "system", "content": "SYSTEM"})
        self.assertEqual(kwargs["response_format"]["type"], "json_schema")
