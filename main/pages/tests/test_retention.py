from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.core.management import call_command
from pages.models import BotUser, Conversation, ConversationMessage


class RetentionTests(TestCase):
    def test_prunes_messages_older_than_cutoff(self):
        user = BotUser.objects.create(name="A", user_id=1, user_name="a")
        conv = Conversation.active_for(user)
        old = ConversationMessage.objects.create(conversation=conv, role="client", text="old")
        new = ConversationMessage.objects.create(conversation=conv, role="client", text="new")
        # auto_now_add can't be set on create; backdate via update()
        ConversationMessage.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=120))
        call_command("prune_conversations", days=90)
        ids = list(ConversationMessage.objects.values_list("id", flat=True))
        self.assertEqual(ids, [new.id])
