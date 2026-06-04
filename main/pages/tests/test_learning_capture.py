from unittest import mock
from django.test import TestCase
from pages.models import (
    BotUser, Conversation, ConversationMessage, AIDecisionLog, FAQSuggestion,
)
from pages.handlers import group as group_handler


def staff_reply(target_user_id, text, group_id=-100, message_id=42):
    return {
        "chat": {"id": group_id, "type": "supergroup"},
        "message_id": message_id,
        "text": text,
        "reply_to_message": {
            "message_id": 7, "from": {"is_bot": True},
            "forward_origin": {"type": "user", "sender_user": {"id": target_user_id}},
        },
    }


class LearningCaptureTests(TestCase):
    def setUp(self):
        self.user = BotUser.objects.create(name="Mijoz", user_id=555, user_name="m")
        self.conv = Conversation.active_for(self.user)
        ConversationMessage.objects.create(conversation=self.conv, role="client",
                                            text="Tahlil narxi qancha?")

    @mock.patch("pages.TelegramAPI.copyMessage")
    def test_captures_general_escalation(self, copy):
        AIDecisionLog.objects.create(conversation=self.conv, intent="info_question",
                                     action="escalate", confidence=0.2)
        group_handler.handle_group_message(staff_reply(555, "Umumiy tahlil 80000 UZS"))
        s = FAQSuggestion.objects.get()
        self.assertEqual(s.question, "Tahlil narxi qancha?")
        self.assertEqual(s.answer, "Umumiy tahlil 80000 UZS")
        self.assertEqual(s.status, "pending")

    @mock.patch("pages.TelegramAPI.copyMessage")
    def test_does_not_capture_personal_data(self, copy):
        AIDecisionLog.objects.create(conversation=self.conv, intent="personal_data_request",
                                     action="escalate", confidence=0.9)
        group_handler.handle_group_message(staff_reply(555, "Sizning natijangiz tayyor"))
        self.assertEqual(FAQSuggestion.objects.count(), 0)

    @mock.patch("pages.TelegramAPI.copyMessage")
    def test_ai_resume_does_not_capture(self, copy):
        group_handler.handle_group_message(staff_reply(555, "/ai_resume"))
        self.assertEqual(FAQSuggestion.objects.count(), 0)
