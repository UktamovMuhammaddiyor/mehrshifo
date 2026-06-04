from unittest import mock
from django.test import SimpleTestCase
from pages import TelegramAPI


class TelegramAPITests(SimpleTestCase):
    @mock.patch("pages.TelegramAPI.requests.post")
    def test_copy_message_payload(self, post):
        post.return_value.json.return_value = {"ok": True}
        TelegramAPI.copyMessage(10, 20, 30)
        url, payload = post.call_args.args[0], post.call_args.args[1]
        self.assertTrue(url.endswith("copyMessage"))
        self.assertEqual(payload, {"chat_id": 10, "from_chat_id": 20, "message_id": 30})

    @mock.patch("pages.TelegramAPI.requests.post")
    def test_send_message_reply_sets_reply_parameters(self, post):
        post.return_value.json.return_value = {"ok": True}
        TelegramAPI.sendMessageReply(5, "salom", 99)
        payload = post.call_args.args[1]
        self.assertEqual(payload["chat_id"], 5)
        self.assertIn("reply_parameters", payload)
        self.assertIn("99", payload["reply_parameters"])

    def test_escape_html(self):
        self.assertEqual(TelegramAPI.escape_html("<b>&"), "&lt;b&gt;&amp;")
        self.assertEqual(TelegramAPI.escape_html(None), "")
