from django.test import TestCase
from pages.models import Service, Doctor, ClinicInfo, FAQ


class KBModelTests(TestCase):
    def test_service_str_and_defaults(self):
        s = Service.objects.create(name="Konsultatsiya", price="150000.00")
        self.assertEqual(str(s), "Konsultatsiya")
        self.assertEqual(s.currency, "UZS")
        self.assertTrue(s.is_active)

    def test_clinicinfo_get_returns_singleton_or_none(self):
        self.assertIsNone(ClinicInfo.get())
        ClinicInfo.objects.create(name="Mehr Shifo")
        self.assertEqual(ClinicInfo.get().name, "Mehr Shifo")

    def test_faq_and_doctor_create(self):
        FAQ.objects.create(question="Ish vaqti?", answer="09:00-18:00")
        d = Doctor.objects.create(full_name="Dr. Aliyev", specialty="Kardiolog")
        self.assertEqual(str(d), "Dr. Aliyev")
