from django.test import TestCase, Client


class MiniAppPageTests(TestCase):
    def test_composer_page_renders_form(self):
        r = Client().get("/miniapp/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "telegram-web-app.js")
        self.assertContains(r, 'id="title"')
        self.assertContains(r, 'id="body"')
