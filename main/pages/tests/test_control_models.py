from django.test import TestCase
from pages.models import AISettings, ProcessedUpdate


class ControlModelTests(TestCase):
    def test_aisettings_get_creates_singleton_with_defaults(self):
        s = AISettings.get()
        self.assertFalse(s.is_enabled)            # AI ships OFF by default
        self.assertEqual(s.model_name, "gpt-4o")
        self.assertEqual(s.confidence_threshold, 0.6)
        self.assertEqual(AISettings.objects.count(), 1)
        self.assertEqual(AISettings.get().id, s.id)  # reused, not duplicated

    def test_processed_update_unique(self):
        ProcessedUpdate.objects.create(update_id=1)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            ProcessedUpdate.objects.create(update_id=1)
