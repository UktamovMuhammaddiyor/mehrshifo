from unittest import mock
from django.test import TestCase
from pages.models import BotUser, ConversationMessage
from pages.ai.pipeline import Outcome


class TasksTests(TestCase):
    def setUp(self):
        self.user = BotUser.objects.create(name="A", user_id=1, user_name="a")

    @mock.patch("pages.handlers.private_ai.deliver")
    @mock.patch("pages.ai.pipeline.run", return_value=Outcome(action="answer", client_text="ok"))
    def test_saves_client_message_and_delivers(self, mock_run, mock_deliver):
        from pages.tasks import process_client_message
        process_client_message(self.user.user_id, "salom", 55)
        self.assertEqual(
            ConversationMessage.objects.filter(role="client", text="salom").count(), 1
        )
        mock_run.assert_called_once()
        mock_deliver.assert_called_once()

    @mock.patch("pages.handlers.private_ai.deliver")
    @mock.patch("pages.ai.pipeline.run")
    def test_unknown_user_is_noop(self, mock_run, mock_deliver):
        from pages.tasks import process_client_message
        process_client_message(999999, "salom", 1)
        mock_run.assert_not_called()
        mock_deliver.assert_not_called()
