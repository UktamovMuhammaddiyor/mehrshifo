from unittest import mock
from django.test import TestCase
from pages.models import BotUser, ChannelBot, ContentDraft
from pages.publishing import publishers


def make_draft():
    u = BotUser.objects.create(name="S", user_id=1, user_name="s")
    return ContentDraft.objects.create(created_by=u, kind="post", title="Salom", body="Tana matni")


class WordPressPublisherTests(TestCase):
    @mock.patch("pages.publishing.publishers.requests.post")
    def test_publish_success_returns_url(self, post):
        post.return_value.status_code = 201
        post.return_value.json.return_value = {"link": "https://clinic/x", "id": 5}
        with mock.patch("pages.creditionals.WORDPRESS_URL", "https://clinic"), \
             mock.patch("pages.creditionals.WORDPRESS_USER", "u"), \
             mock.patch("pages.creditionals.WORDPRESS_APP_PASSWORD", "p"):
            res = publishers.WordPressPublisher().publish(make_draft())
        self.assertTrue(res["ok"])
        self.assertEqual(res["url"], "https://clinic/x")
        self.assertTrue(post.call_args.args[0].endswith("/wp-json/wp/v2/posts"))

    @mock.patch("pages.publishing.publishers.requests.post")
    def test_publish_failure_returns_error(self, post):
        post.return_value.status_code = 401
        post.return_value.json.return_value = {"message": "bad auth"}
        res = publishers.WordPressPublisher().publish(make_draft())
        self.assertFalse(res["ok"])
        self.assertIn("bad auth", res["error"])


class ChannelPublisherTests(TestCase):
    @mock.patch("pages.publishing.publishers.sentMessage")
    def test_no_channel_registered(self, sent):
        res = publishers.ChannelPublisher().publish(make_draft())
        self.assertFalse(res["ok"])
        sent.assert_not_called()

    @mock.patch("pages.publishing.publishers.sentMessage",
                return_value={"ok": True, "result": {"message_id": 9}})
    def test_publish_to_channel(self, sent):
        ChannelBot.objects.create(name="C", chat_id=-100)
        res = publishers.ChannelPublisher().publish(make_draft())
        self.assertTrue(res["ok"])
        self.assertEqual(res["message_id"], 9)

    @mock.patch("pages.publishing.publishers.sentMessage",
                return_value={"ok": True, "result": {"message_id": 1}})
    def test_channel_escapes_html(self, sent):
        ChannelBot.objects.create(name="C", chat_id=-100)
        u = BotUser.objects.create(name="S", user_id=2, user_name="s")
        draft = ContentDraft.objects.create(created_by=u, kind="post",
                                            title="A & B <x>", body="1 < 2")
        publishers.ChannelPublisher().publish(draft)
        text = sent.call_args.args[2]
        self.assertIn("A &amp; B &lt;x&gt;", text)
        self.assertIn("1 &lt; 2", text)


class BotUsersPublisherTests(TestCase):
    @mock.patch("pages.publishing.publishers.sentMessage", return_value={"ok": True})
    def test_broadcast_counts(self, sent):
        BotUser.objects.create(name="A", user_id=10, user_name="a")
        BotUser.objects.create(name="B", user_id=11, user_name="b")
        res = publishers.BotUsersPublisher().publish(make_draft())
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], sent.call_count)
        self.assertGreaterEqual(res["count"], 2)
