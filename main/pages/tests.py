"""
First real test suite for the getPost Telegram webhook dispatcher.

Strategy (see .claude/skills/bot-testing/SKILL.md):
  - POST crafted Telegram update payloads to /getpost/ with Django's test Client.
  - Assert on DB state and on which outbound Telegram calls were made.
  - Mock the outbound boundary so tests make ZERO real network calls. The wrappers
    (sentMessage, answerCallbackQuery, getMemberInformation, forwardMessage,
    deleteMessage) are imported INTO the pages.views namespace, so we patch them
    there. Two branches use a direct requests.post(BOT_URL + ...) inside views.py
    (admin-promotion success, group activation), so we also patch
    pages.views.requests.post.

These tests pin the bot's behavior at the getPost boundary. Three bugs originally
surfaced here -- UnboundLocalError in /start, AttributeError in the check/done
callbacks when no AboutMessage row exists, and IndexError when no GroupBot row
exists -- have since been fixed in views.py; the corresponding tests now assert the
corrected behavior.
"""
import json
from unittest.mock import patch

from django.test import TestCase, Client

from pages.models import (
    BotUser,
    AboutMessage,
    ChannelBot,
    ChannelMessage,
    GroupBot,
    AutoAnswer,
)

PASSWORD = "WTlJgvNGS3PZGOv"


# --------------------------------------------------------------------------- #
# (a) Reusable update-fixture factories
# --------------------------------------------------------------------------- #
def make_message(text, user_id=1, chat_type="private", message_id=10, **extra):
    """A Telegram `message` update. `extra` is merged into the message dict so
    callers can attach reply_to_message, photo, caption, etc."""
    return {
        "message": {
            "message_id": message_id,
            "text": text,
            "from": {"id": user_id, "first_name": "T", "is_bot": False},
            "chat": {"id": user_id, "type": chat_type},
            **extra,
        }
    }


def make_callback(data, user_id=1, message_id=10, cq_id="cq1"):
    """A Telegram `callback_query` update (inline button press)."""
    return {
        "callback_query": {
            "id": cq_id,
            "data": data,
            "from": {"id": user_id},
            "message": {"message_id": message_id},
        }
    }


def make_my_chat_member(chat_id, chat_type, status, title="Chat", username=None):
    """A Telegram `my_chat_member` update (bot's membership/role changed)."""
    chat = {"id": chat_id, "type": chat_type, "title": title}
    if username is not None:
        chat["username"] = username
    return {
        "my_chat_member": {
            "chat": chat,
            "new_chat_member": {"status": status},
        }
    }


class GetPostTestBase(TestCase):
    """Patches every outbound boundary so tests make zero network calls."""

    URL = "/getpost/"

    def setUp(self):
        self.client = Client()

        # Outbound wrappers, patched in the pages.views namespace.
        self.p_sent = patch("pages.views.sentMessage").start()
        self.p_answer = patch("pages.views.answerCallbackQuery").start()
        self.p_member = patch("pages.views.getMemberInformation").start()
        self.p_forward = patch("pages.views.forwardMessage").start()
        self.p_delete = patch("pages.views.deleteMessage").start()
        # Two branches bypass the wrappers and call requests.post directly.
        self.p_requests = patch("pages.views.requests.post").start()

        # Sensible defaults.
        self.p_sent.return_value = {}
        self.p_member.return_value = ""  # not subscribed by default
        self.addCleanup(patch.stopall)

    def post(self, payload):
        return self.client.post(
            self.URL,
            data=json.dumps(payload),
            content_type="application/json",
        )


# --------------------------------------------------------------------------- #
# (b) /getadmin + password admin-promotion flow
# --------------------------------------------------------------------------- #
class AdminPromotionTests(GetPostTestBase):
    def _seed_user(self, user_id=1):
        # /getadmin does BotUser.objects.get(...) first, so the user must
        # already exist (normally created by an earlier /start).
        return BotUser.objects.create(name="T", user_id=user_id, user_name="")

    def test_getadmin_sets_status_and_prompts(self):
        self._seed_user()
        resp = self.post(make_message("/getadmin"))
        self.assertEqual(resp.status_code, 200)
        user = BotUser.objects.get(user_id=1)
        self.assertEqual(user.status, "getAdmin")
        self.p_sent.assert_called_once()
        self.assertFalse(user.is_admin)

    def test_correct_password_promotes_admin_and_clears_status(self):
        user = self._seed_user()
        user.status = "getAdmin"
        user.save()

        resp = self.post(make_message(PASSWORD))
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_admin)
        self.assertEqual(user.status, "")
        # Success path posts the admin reply-keyboard via requests.post directly.
        self.assertTrue(self.p_requests.called)

    def test_wrong_password_rejected_and_status_cleared(self):
        user = self._seed_user()
        user.status = "getAdmin"
        user.save()

        resp = self.post(make_message("not-the-password"))
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_admin)
        self.assertEqual(user.status, "")  # status reset on failure
        self.p_sent.assert_called_once()  # "Parol nato'g'ri"
        self.assertFalse(self.p_requests.called)

    def test_getadmin_unknown_user_raises_does_not_exist(self):
        # /getadmin from a user who never did /start: line 82 does
        # BotUser.objects.get(...) with no fallback -> DoesNotExist (500).
        # Documents current behavior: getPost has no error handling here.
        with self.assertRaises(BotUser.DoesNotExist):
            self.post(make_message("/getadmin", user_id=999))


# --------------------------------------------------------------------------- #
# (c) Forced-subscription callback_query path: `check`
# --------------------------------------------------------------------------- #
class CheckSubscriptionCallbackTests(GetPostTestBase):
    def _seed_about(self, chat_id=-100123, is_active=True):
        return AboutMessage.objects.create(
            link="https://t.me/x", chat_id=chat_id, is_active=is_active
        )

    def test_check_subscribed_marks_user_and_alerts(self):
        self._seed_about()
        BotUser.objects.create(name="T", user_id=1, user_name="")
        self.p_member.return_value = "member"  # subscribed

        resp = self.post(make_callback("check"))
        self.assertEqual(resp.status_code, 200)

        user = BotUser.objects.get(user_id=1)
        self.assertTrue(user.is_subcribe)
        self.p_answer.assert_called_once()
        # show_alert=True is the 3rd positional arg
        self.assertTrue(self.p_answer.call_args.args[2])

    def test_check_not_subscribed_does_not_mark_user(self):
        self._seed_about()
        BotUser.objects.create(name="T", user_id=1, user_name="")
        self.p_member.return_value = ""  # not a member

        resp = self.post(make_callback("check"))
        self.assertEqual(resp.status_code, 200)

        user = BotUser.objects.get(user_id=1)
        self.assertFalse(user.is_subcribe)
        self.p_answer.assert_called_once()

    def test_turn_on_subscription_activates_config(self):
        self._seed_about(is_active=False)
        resp = self.post(make_callback("turn_on_subcription"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(AboutMessage.objects.first().is_active)
        self.p_delete.assert_called_once()

    def test_turn_off_subscription_deactivates_config(self):
        self._seed_about(is_active=True)
        resp = self.post(make_callback("turn_off_subcription"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(AboutMessage.objects.first().is_active)
        self.p_delete.assert_called_once()

    def test_check_with_empty_about_table_does_not_crash(self):
        # FIXED: with no AboutMessage row, `message` is falsy, so the guarded
        # `if message and userHasMemberOfChannel(...)` short-circuits to the else
        # branch instead of raising AttributeError on message.chat_id. The user is
        # not marked subscribed (there is no channel to verify membership against).
        BotUser.objects.create(name="T", user_id=1, user_name="")
        self.p_member.return_value = "member"
        resp = self.post(make_callback("check"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(BotUser.objects.get(user_id=1).is_subcribe)
        self.p_answer.assert_called_once()


# --------------------------------------------------------------------------- #
# (d) my_chat_member auto-registration of ChannelBot / GroupBot
# --------------------------------------------------------------------------- #
class MyChatMemberTests(GetPostTestBase):
    def test_channel_registers_channelbot_with_username(self):
        resp = self.post(
            make_my_chat_member(
                chat_id=-100500, chat_type="channel",
                status="administrator", title="My Chan", username="mychan",
            )
        )
        self.assertEqual(resp.status_code, 200)
        bot = ChannelBot.objects.get(chat_id=-100500)
        self.assertEqual(bot.name, "My Chan")
        self.assertEqual(bot.chat_link, "https://t.me/mychan")

    def test_channel_registers_channelbot_without_username(self):
        resp = self.post(
            make_my_chat_member(
                chat_id=-100501, chat_type="channel",
                status="administrator", title="Private Chan",  # no username
            )
        )
        self.assertEqual(resp.status_code, 200)
        bot = ChannelBot.objects.get(chat_id=-100501)
        self.assertEqual(bot.name, "Private Chan")
        self.assertEqual(bot.chat_link, "")

    def test_channel_does_not_duplicate_existing(self):
        ChannelBot.objects.create(name="Existing", chat_id=-100502, chat_link="x")
        self.post(
            make_my_chat_member(
                chat_id=-100502, chat_type="channel",
                status="administrator", title="New Title", username="new",
            )
        )
        # get() inside try succeeds -> no create; still exactly one row, unchanged.
        self.assertEqual(ChannelBot.objects.filter(chat_id=-100502).count(), 1)
        self.assertEqual(ChannelBot.objects.get(chat_id=-100502).name, "Existing")

    def test_group_admin_registers_groupbot_and_prompts_password(self):
        resp = self.post(
            make_my_chat_member(
                chat_id=-200600, chat_type="supergroup",
                status="administrator", title="Supp Group", username="suppgroup",
            )
        )
        self.assertEqual(resp.status_code, 200)
        group = GroupBot.objects.get(group_id=-200600)
        self.assertEqual(group.name, "Supp Group")
        self.assertEqual(group.group_link, "https://t.me/suppgroup")
        self.assertFalse(group.is_active)  # activated only by password
        # Prompts for the activation password.
        self.p_sent.assert_called_once()

    def test_group_non_admin_status_does_not_register(self):
        # Only status == "administrator" registers a GroupBot.
        resp = self.post(
            make_my_chat_member(
                chat_id=-200601, chat_type="group",
                status="member", title="Plain Group",
            )
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(GroupBot.objects.filter(group_id=-200601).exists())
        self.p_sent.assert_not_called()


# --------------------------------------------------------------------------- #
# Group password activation (the other PASSWORD gate, in a group chat)
# --------------------------------------------------------------------------- #
class GroupActivationTests(GetPostTestBase):
    PROMPT = "Iltimos guruhni qo'shish uchun parolni tering."

    def _group_reply(self, text, group_id, reply_text=None):
        if reply_text is None:
            reply_text = self.PROMPT
        return make_message(
            text,
            user_id=group_id,
            chat_type="supergroup",
            reply_to_message={
                "message_id": 5,
                "text": reply_text,
                "from": {"id": 42, "is_bot": True},
            },
        )

    def test_correct_password_activates_group(self):
        GroupBot.objects.create(name="G", group_id=-200700, is_active=False)
        resp = self.post(self._group_reply(PASSWORD, group_id=-200700))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(GroupBot.objects.get(group_id=-200700).is_active)
        self.p_delete.assert_called_once()  # deletes the prompt message
        self.assertTrue(self.p_requests.called)  # confirmation via requests.post

    def test_wrong_password_does_not_activate(self):
        GroupBot.objects.create(name="G", group_id=-200701, is_active=False)
        resp = self.post(self._group_reply("nope", group_id=-200701))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(GroupBot.objects.get(group_id=-200701).is_active)


# --------------------------------------------------------------------------- #
# (e) Single-row config empty-table cases
# --------------------------------------------------------------------------- #
class SingleRowConfigEmptyTableTests(GetPostTestBase):
    def test_start_with_empty_about_creates_user(self):
        # /start with NO AboutMessage row: getUser() creates the user and the
        # `if message:` about-message block is skipped.
        self.assertEqual(AboutMessage.objects.count(), 0)
        resp = self.post(make_message("/start", user_id=77))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(BotUser.objects.filter(user_id=77).exists())

    def test_addAnswer_then_message_creates_autoanswer_on_empty_table(self):
        # /addAnswer sets status, follow-up text creates the single AutoAnswer row.
        admin = BotUser.objects.create(
            name="A", user_id=1, user_name="", is_admin=True
        )
        self.post(make_message("/addAnswer"))
        admin.refresh_from_db()
        self.assertEqual(admin.status, "addinganswer")

        self.assertEqual(AutoAnswer.objects.count(), 0)
        self.post(make_message("Salom javob"))
        admin.refresh_from_db()
        self.assertEqual(admin.status, "")
        self.assertEqual(AutoAnswer.objects.count(), 1)
        self.assertEqual(AutoAnswer.objects.first().text, "Salom javob")

    def test_start_with_existing_about_greets_and_creates_user(self):
        # FIXED: `user = getUser(response)` now runs before the `if message:`
        # block, so /start with a non-empty AboutMessage table no longer raises
        # UnboundLocalError. The user is created and the about-message is sent.
        AboutMessage.objects.create(link="https://t.me/x", chat_id=-1, is_active=True)
        resp = self.post(make_message("/start", user_id=88))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(BotUser.objects.filter(user_id=88).exists())
        self.p_sent.assert_called_once()

    def test_non_admin_message_with_no_groupbot_acknowledges_without_forward(self):
        # FIXED: with no GroupBot row, GroupBot.objects.first() returns None and the
        # forward is guarded, so there is no IndexError. The user still receives the
        # default acknowledgement, but nothing is forwarded.
        BotUser.objects.create(name="U", user_id=5, user_name="", is_admin=False)
        self.assertEqual(GroupBot.objects.count(), 0)
        resp = self.post(make_message("salom", user_id=5))
        self.assertEqual(resp.status_code, 200)
        self.p_sent.assert_called_once_with("Message", 5, "Murojatiz qabul qilindi.")
        self.p_forward.assert_not_called()
