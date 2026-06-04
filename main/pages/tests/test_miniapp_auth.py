import hmac, hashlib, json, time
from urllib.parse import urlencode
from unittest import mock
from django.test import SimpleTestCase
from pages.publishing.auth import validate_init_data, is_allowed

TOKEN = "12345:test-token"


def sign(params, token=TOKEN):
    dcs = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode({**params, "hash": h})


def base_params():
    return {"auth_date": str(int(time.time())),
            "user": json.dumps({"id": 777, "first_name": "S"})}


class InitDataAuthTests(SimpleTestCase):
    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    def test_valid_init_data_returns_user(self):
        user = validate_init_data(sign(base_params()))
        self.assertEqual(user["id"], 777)

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    def test_tampered_hash_rejected(self):
        raw = sign(base_params())
        self.assertIsNone(validate_init_data(raw + "0"))  # corrupt the hash tail

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    def test_stale_auth_date_rejected(self):
        params = {"auth_date": "1", "user": json.dumps({"id": 1})}
        self.assertIsNone(validate_init_data(sign(params)))

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    def test_wrong_token_rejected(self):
        raw = sign(base_params(), token="99:other")
        self.assertIsNone(validate_init_data(raw))

    @mock.patch("pages.creditionals.ADMIN_USER_IDS", [777])
    def test_is_allowed_respects_allowlist(self):
        self.assertTrue(is_allowed({"id": 777}))
        self.assertFalse(is_allowed({"id": 1}))

    @mock.patch("pages.creditionals.ADMIN_USER_IDS", [])
    def test_is_allowed_fails_closed_when_empty(self):
        self.assertFalse(is_allowed({"id": 777}))

    @mock.patch("pages.creditionals.BOT_TOKEN", TOKEN)
    def test_non_dict_user_rejected(self):
        raw = sign({"auth_date": str(int(time.time())), "user": json.dumps([1, 2])})
        self.assertIsNone(validate_init_data(raw))

    @mock.patch("pages.creditionals.BOT_TOKEN", "")
    def test_empty_bot_token_rejected(self):
        raw = sign({"auth_date": str(int(time.time())), "user": json.dumps({"id": 1})}, token="")
        self.assertIsNone(validate_init_data(raw))

    def test_is_allowed_handles_non_dict(self):
        self.assertFalse(is_allowed(None))
        self.assertFalse(is_allowed([1, 2]))
