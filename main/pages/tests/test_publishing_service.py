from unittest import mock
from django.test import TestCase
from pages.models import BotUser, ContentDraft
from pages.publishing import service


class ServiceTests(TestCase):
    def setUp(self):
        self.user = BotUser.objects.create(name="S", user_id=1, user_name="s")

    @mock.patch("django_q.tasks.async_task")
    def test_start_generation_creates_draft_and_enqueues(self, async_task):
        draft = service.start_generation(self.user, "post", "Aksiya", "https://x")
        self.assertEqual(draft.status, "generating")
        self.assertEqual(draft.mode, "ai")
        async_task.assert_called_once_with("pages.tasks.generate_content_job", draft.id)

    @mock.patch("pages.publishing.generator.generate_content",
                return_value={"title": "T", "body": "Tayyor matn"})
    def test_run_generation_fills_body_and_marks_ready(self, gen):
        draft = ContentDraft.objects.create(created_by=self.user, kind="post",
                                            title="T", status="generating")
        service.run_generation(draft.id)
        draft.refresh_from_db()
        self.assertEqual(draft.status, "ready")
        self.assertEqual(draft.body, "Tayyor matn")

    @mock.patch("pages.publishing.generator.generate_content", side_effect=RuntimeError("boom"))
    def test_run_generation_marks_failed_on_error(self, gen):
        draft = ContentDraft.objects.create(created_by=self.user, kind="post",
                                            title="T", status="generating")
        service.run_generation(draft.id)
        draft.refresh_from_db()
        self.assertEqual(draft.status, "failed")
        self.assertIn("boom", draft.error)

    def test_publish_draft_records_per_target_results(self):
        draft = ContentDraft.objects.create(created_by=self.user, kind="post", title="T", body="B")

        class OK:
            def publish(self, d):
                return {"ok": True, "url": "https://x"}

        class Bad:
            def publish(self, d):
                return {"ok": False, "error": "no"}

        with mock.patch.dict(service.PUBLISHERS, {"site": OK, "channel": Bad}, clear=True):
            results = service.publish_draft(draft, {"site": True, "channel": True})
        self.assertEqual(results["site"]["url"], "https://x")
        self.assertFalse(results["channel"]["ok"])
        draft.refresh_from_db()
        self.assertEqual(draft.status, "published")  # any target ok → published
