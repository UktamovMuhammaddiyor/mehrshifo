from django.test import TestCase
from django.conf import settings
from django.core.cache import cache


class InfraTests(TestCase):
    def test_django_q_installed(self):
        self.assertIn("django_q", settings.INSTALLED_APPS)

    def test_q_cluster_uses_orm_broker(self):
        self.assertEqual(settings.Q_CLUSTER["orm"], "default")
        # django-q2 requires timeout < retry
        self.assertLess(settings.Q_CLUSTER["timeout"], settings.Q_CLUSTER["retry"])

    def test_shared_cache_roundtrip(self):
        cache.set("infra_probe", "ok", 30)
        self.assertEqual(cache.get("infra_probe"), "ok")
