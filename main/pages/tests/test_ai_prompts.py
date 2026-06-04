from django.test import TestCase
from pages.models import AISettings, Conversation, BotUser, ConversationMessage
from pages.ai.prompts import build_system_prompt, build_messages


class PromptTests(TestCase):
    def test_system_prompt_embeds_kb_and_safety(self):
        s = AISettings.get()
        s.persona_extra = "PERSONA_MARKER"
        prompt = build_system_prompt("KB_SNAPSHOT_MARKER", s)
        self.assertIn("KB_SNAPSHOT_MARKER", prompt)
        self.assertIn("PERSONA_MARKER", prompt)
        # anti-hallucination + no-medical rules present (Uzbek keywords)
        self.assertIn("taxmin", prompt.lower())
        self.assertIn("tashxis", prompt.lower())

    def test_build_messages_maps_roles(self):
        user = BotUser.objects.create(name="A", user_id=1, user_name="a")
        conv = Conversation.active_for(user)
        h1 = ConversationMessage.objects.create(conversation=conv, role="client", text="salom")
        h2 = ConversationMessage.objects.create(conversation=conv, role="ai", text="Assalomu alaykum")
        msgs = build_messages([h1, h2], "narxlar qancha?")
        self.assertEqual(msgs[0], {"role": "user", "content": "salom"})
        self.assertEqual(msgs[1], {"role": "assistant", "content": "Assalomu alaykum"})
        self.assertEqual(msgs[-1], {"role": "user", "content": "narxlar qancha?"})
