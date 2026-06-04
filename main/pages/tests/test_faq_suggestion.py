from django.test import TestCase
from pages.models import FAQSuggestion, FAQ


class FAQSuggestionTests(TestCase):
    def test_defaults_to_pending(self):
        s = FAQSuggestion.objects.create(question="Ish vaqti?", answer="09:00-18:00")
        self.assertEqual(s.status, "pending")
        self.assertIsNone(s.reviewed_by)

    def test_approve_creates_faq_and_marks_approved(self):
        s = FAQSuggestion.objects.create(question="Narx?", answer="150000 UZS")
        faq = s.approve(reviewer="admin")
        self.assertIsInstance(faq, FAQ)
        self.assertEqual(faq.question, "Narx?")
        self.assertEqual(faq.answer, "150000 UZS")
        s.refresh_from_db()
        self.assertEqual(s.status, "approved")
        self.assertEqual(s.reviewed_by, "admin")

    def test_approve_is_idempotent(self):
        s = FAQSuggestion.objects.create(question="Q", answer="A")
        s.approve(reviewer="x")
        s.approve(reviewer="x")  # second call must not create a duplicate FAQ
        self.assertEqual(FAQ.objects.filter(question="Q").count(), 1)
