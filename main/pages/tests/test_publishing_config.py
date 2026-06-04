from django.test import TestCase
from pages.models import BotUser, ContentDraft


class PublishingConfigTests(TestCase):
    def test_content_draft_defaults(self):
        u = BotUser.objects.create(name="Staff", user_id=1, user_name="s")
        d = ContentDraft.objects.create(created_by=u, kind="post", mode="ai", title="T")
        self.assertEqual(d.status, "draft")
        self.assertEqual(d.targets, {})
        self.assertEqual(d.publish_results, {})

    def test_config_symbols_exist(self):
        from pages import creditionals
        for name in ("WORDPRESS_URL", "WORDPRESS_USER", "WORDPRESS_APP_PASSWORD", "MINIAPP_URL"):
            self.assertTrue(hasattr(creditionals, name))
