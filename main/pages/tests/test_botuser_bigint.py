from django.test import TestCase
from pages.models import BotUser


class BotUserBigIntTests(TestCase):
    def test_large_telegram_id_is_stored(self):
        big = 8_000_000_000  # exceeds 32-bit signed int
        u = BotUser.objects.create(name="Big", user_id=big, user_name="big")
        u.refresh_from_db()
        self.assertEqual(u.user_id, big)
