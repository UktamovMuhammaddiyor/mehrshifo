import hmac, hashlib, json, time
from urllib.parse import urlencode
from unittest import mock
from django.test import TestCase, Client

TOKEN = "12345:test-token"


def sign(params, token=TOKEN):
    dcs = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode({**params, "hash": h})


def valid_init(uid=777):
    return sign({"auth_date": str(int(time.time())),
                 "user": json.dumps({"id": uid, "first_name": "S"})})


class MiniAppApiTests(TestCase):
    def setUp(self):
        self.c = Client()

    def test_generate_forbidden_without_initdata(self):
        r = self.c.post("/miniapp/api/generate", data="{}", content_type="application/json")
        self.assertEqual(r.status_code, 403)

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    @mock.patch("pages.creditionals.ADMIN_USER_IDS", [777])
    @mock.patch("pages.miniapp.views.start_generation")
    def test_generate_authed_enqueues(self, start):
        start.return_value = mock.Mock(id=9, status="generating")
        r = self.c.post("/miniapp/api/generate",
                        data=json.dumps({"kind": "post", "title": "T"}),
                        content_type="application/json",
                        HTTP_X_TELEGRAM_INIT_DATA=valid_init())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["draft_id"], 9)
        start.assert_called_once()

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    @mock.patch("pages.creditionals.ADMIN_USER_IDS", [777])
    @mock.patch("pages.miniapp.views.publish_draft", return_value={"channel": {"ok": True}})
    def test_publish_manual_creates_draft_and_publishes(self, pub):
        r = self.c.post("/miniapp/api/publish",
                        data=json.dumps({"kind": "post", "title": "T", "body": "B",
                                         "targets": {"channel": True}}),
                        content_type="application/json",
                        HTTP_X_TELEGRAM_INIT_DATA=valid_init())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["results"]["channel"]["ok"])
        pub.assert_called_once()

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    @mock.patch("pages.creditionals.ADMIN_USER_IDS", [42])  # 777 not allowed
    def test_non_allowlisted_forbidden(self):
        r = self.c.post("/miniapp/api/generate", data=json.dumps({"kind": "post", "title": "T"}),
                        content_type="application/json", HTTP_X_TELEGRAM_INIT_DATA=valid_init(777))
        self.assertEqual(r.status_code, 403)

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    @mock.patch("pages.creditionals.ADMIN_USER_IDS", [777])
    def test_malformed_body_returns_400(self):
        r = self.c.post("/miniapp/api/generate", data="{not json",
                        content_type="application/json",
                        HTTP_X_TELEGRAM_INIT_DATA=valid_init())
        self.assertEqual(r.status_code, 400)
