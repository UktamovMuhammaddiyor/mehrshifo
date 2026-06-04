from django.test import TestCase
from pages.models import Service, ClinicInfo
from pages.knowledge.snapshot import get_kb_snapshot, kb_version


class KBSnapshotTests(TestCase):
    def test_snapshot_contains_service_and_price(self):
        ClinicInfo.objects.create(name="Mehr Shifo", working_hours="09:00-18:00")
        Service.objects.create(name="MRT", price="500000.00")
        snap = get_kb_snapshot()
        self.assertIn("MRT", snap)
        self.assertIn("500000", snap)
        self.assertIn("09:00-18:00", snap)

    def test_price_change_invalidates_cache(self):
        s = Service.objects.create(name="UZI", price="100000.00")
        self.assertIn("100000", get_kb_snapshot())
        s.price = "120000.00"
        s.save()  # post_save signal must clear the cache
        snap = get_kb_snapshot()
        self.assertIn("120000", snap)
        self.assertNotIn("100000", snap)

    def test_kb_version_is_stable_hash(self):
        v1 = kb_version()
        self.assertEqual(len(v1), 8)
        self.assertEqual(v1, kb_version())
