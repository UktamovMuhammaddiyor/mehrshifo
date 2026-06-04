from unittest import mock
from django.test import TestCase
from pages.models import BotUser, Conversation
from pages.handlers import group as group_handler


def reply_update(target_user_id, text, group_id=-100, message_id=42):
    return {
        "chat": {"id": group_id, "type": "supergroup"},
        "message_id": message_id,
        "text": text,
        "reply_to_message": {
            "message_id": 7,
            "from": {"is_bot": True},
            "forward_origin": {"type": "user", "sender_user": {"id": target_user_id}},
        },
    }


class GroupHandlerTests(TestCase):
    def setUp(self):
        self.user = BotUser.objects.create(name="Mijoz", user_id=555, user_name="m")
        self.conv = Conversation.active_for(self.user)

    @mock.patch("pages.TelegramAPI.copyMessage")
    def test_staff_reply_relays_and_sets_handoff(self, copy):
        handled = group_handler.handle_group_message(reply_update(555, "Javob shu"))
        self.assertTrue(handled)
        copy.assert_called_once_with(555, -100, 42)
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.status, "handoff")

    @mock.patch("pages.TelegramAPI.copyMessage")
    def test_ai_resume_command_reactivates(self, copy):
        self.conv.status = "handoff"; self.conv.save()
        handled = group_handler.handle_group_message(reply_update(555, "/ai_resume"))
        self.assertTrue(handled)
        copy.assert_not_called()
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.status, "active")

    def test_non_forward_reply_is_ignored(self):
        upd = {"chat": {"id": -100, "type": "supergroup"}, "message_id": 1, "text": "x",
               "reply_to_message": {"message_id": 2, "from": {"is_bot": True}}}
        self.assertFalse(group_handler.handle_group_message(upd))
