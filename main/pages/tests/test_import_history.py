import json
import tempfile
from django.test import TestCase
from django.core.management import call_command
from pages.models import FAQSuggestion


class ImportHistoryTests(TestCase):
    def _write(self, data):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, f)
        f.close()
        return f.name

    def test_reply_pairs_become_pending_suggestions(self):
        path = self._write({"messages": [
            {"id": 1, "type": "message", "text": "Ish vaqti qachon?"},
            {"id": 2, "type": "message", "text": "09:00 dan 18:00 gacha", "reply_to_message_id": 1},
            {"id": 3, "type": "message", "text": "Rahmat"},  # no reply → ignored
        ]})
        call_command("import_group_history", path)
        s = FAQSuggestion.objects.get()
        self.assertEqual(s.question, "Ish vaqti qachon?")
        self.assertEqual(s.answer, "09:00 dan 18:00 gacha")
        self.assertEqual(s.status, "pending")

    def test_handles_entity_list_text_and_dedupes(self):
        msgs = {"messages": [
            {"id": 1, "text": ["Manzil ", {"type": "bold", "text": "qayerda"}, "?"]},
            {"id": 2, "text": "Chilonzor 5", "reply_to_message_id": 1},
        ]}
        path = self._write(msgs)
        call_command("import_group_history", path)
        call_command("import_group_history", path)  # re-run must not duplicate
        self.assertEqual(FAQSuggestion.objects.filter(question="Manzil qayerda?").count(), 1)
