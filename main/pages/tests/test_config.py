from django.test import SimpleTestCase
from unittest import mock
import importlib


class ConfigTests(SimpleTestCase):
    def test_admin_user_ids_parsed_as_ints(self):
        with mock.patch.dict("os.environ", {"ADMIN_USER_IDS": "111, 222 ,333"}):
            from pages import creditionals
            importlib.reload(creditionals)
            self.assertEqual(creditionals.ADMIN_USER_IDS, [111, 222, 333])

    def test_admin_user_ids_empty_is_empty_list(self):
        with mock.patch.dict("os.environ", {"ADMIN_USER_IDS": ""}):
            from pages import creditionals
            importlib.reload(creditionals)
            self.assertEqual(creditionals.ADMIN_USER_IDS, [])
