import json
from unittest import mock
from django.test import TestCase, Client
from pages.models import BotUser, ProcessedUpdate


class WebhookTests(TestCase):
    def setUp(self):
        self.c = Client()

    def _post(self, payload, secret=None):
        extra = {}
        if secret is not None:
            extra["HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN"] = secret
        return self.c.post("/getpost/", data=json.dumps(payload),
                           content_type="application/json", **extra)

    @mock.patch("pages.creditionals.TELEGRAM_WEBHOOK_SECRET", "topsecret")
    def test_wrong_secret_rejected(self):
        self.assertEqual(self._post({"update_id": 1}, secret="wrong").status_code, 403)

    def test_duplicate_update_ignored(self):
        payload = {"update_id": 7, "poll": {}}  # no handled branch → harmless no-op
        self.assertEqual(self._post(payload).content, b"working")
        self.assertEqual(self._post(payload).content, b"duplicate")
        self.assertEqual(ProcessedUpdate.objects.filter(update_id=7).count(), 1)

    @mock.patch("django_q.tasks.async_task")
    def test_client_message_enqueued(self, async_task):
        BotUser.objects.create(name="A", user_id=1234, user_name="a")
        self._post({"update_id": 8, "message": {
            "chat": {"id": 1234, "type": "private"},
            "from": {"id": 1234, "first_name": "A"},
            "text": "narxlar qancha?", "message_id": 91,
        }})
        async_task.assert_called_once_with(
            "pages.tasks.process_client_message", 1234, "narxlar qancha?", 91)

    @mock.patch("pages.handlers.group.handle_group_message", return_value=True)
    def test_group_reply_routed(self, handler):
        self._post({"update_id": 9, "message": {
            "chat": {"id": -100, "type": "supergroup"},
            "from": {"id": 5, "first_name": "Staff"}, "message_id": 3, "text": "javob",
            "reply_to_message": {"message_id": 2, "from": {"is_bot": True},
                                 "forward_origin": {"type": "user", "sender_user": {"id": 555}}},
        }})
        handler.assert_called_once()
