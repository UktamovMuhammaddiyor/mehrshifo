from django.test import TestCase
from pages.models import BotUser, Conversation, ConversationMessage


class ConversationModelTests(TestCase):
    def setUp(self):
        self.user = BotUser.objects.create(name="Ali", user_id=12345, user_name="ali")

    def test_active_for_creates_then_reuses(self):
        c1 = Conversation.active_for(self.user)
        c2 = Conversation.active_for(self.user)
        self.assertEqual(c1.id, c2.id)
        self.assertEqual(c1.status, "active")

    def test_handoff_conversation_is_still_returned(self):
        c = Conversation.active_for(self.user)
        c.status = "handoff"
        c.save()
        self.assertEqual(Conversation.active_for(self.user).id, c.id)

    def test_messages_ordered_by_id(self):
        c = Conversation.active_for(self.user)
        ConversationMessage.objects.create(conversation=c, role="client", text="salom")
        ConversationMessage.objects.create(conversation=c, role="ai", text="Assalomu alaykum")
        roles = list(c.messages.values_list("role", flat=True))
        self.assertEqual(roles, ["client", "ai"])
