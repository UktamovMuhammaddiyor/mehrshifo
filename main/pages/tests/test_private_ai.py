from unittest import mock
from django.test import TestCase
from pages.models import BotUser, GroupBot, Conversation, ConversationMessage, AISettings
from pages.ai.pipeline import Outcome
from pages.handlers import private_ai


class PrivateAIDeliverTests(TestCase):
    def setUp(self):
        self.user = BotUser.objects.create(name="A", user_id=1, user_name="a")
        self.conv = Conversation.active_for(self.user)
        GroupBot.objects.create(name="Support", group_id=-100, is_active=True)

    @mock.patch("pages.TelegramAPI.sendMessageReply")
    @mock.patch("pages.TelegramAPI.forwardMessage", return_value={"result": {"message_id": 500}})
    @mock.patch("pages.TelegramAPI.sentMessage")
    def test_answer_sends_client_forwards_and_cards(self, sent, fwd, reply):
        out = Outcome(action="answer", client_text="Ish vaqti 9-18", intent="info_question",
                      confidence=0.9, group_label="🤖 AI")
        private_ai.deliver(out, self.user, "ish vaqti?", 77, self.conv)
        sent.assert_any_call("Message", self.user.user_id, "Ish vaqti 9-18")  # to client
        fwd.assert_called_once_with(-100, self.user.user_id, 77)               # forward to group
        reply.assert_called_once()                                             # card under forward
        self.assertEqual(ConversationMessage.objects.filter(role="ai").count(), 1)

    @mock.patch("pages.TelegramAPI.forwardMessage", return_value={"result": {"message_id": 1}})
    @mock.patch("pages.TelegramAPI.sentMessage")
    def test_complaint_sets_handoff(self, sent, fwd):
        out = Outcome(action="notify", client_text="Uzr", intent="complaint",
                      confidence=0.9, group_label="⚠️ SHIKOYAT", notify=True, set_handoff=True)
        with mock.patch("pages.TelegramAPI.sendMessageReply"):
            private_ai.deliver(out, self.user, "yomon", 80, self.conv)
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.status, "handoff")

    @mock.patch("pages.TelegramAPI.forwardMessage", return_value={"result": {"message_id": 1}})
    @mock.patch("pages.TelegramAPI.sentMessage")
    def test_skip_disabled_uses_legacy_autoanswer_and_forward(self, sent, fwd):
        out = Outcome(action="skip", reason="ai_disabled")
        private_ai.deliver(out, self.user, "salom", 81, self.conv)
        fwd.assert_called_once_with(-100, self.user.user_id, 81)
        # client got an acknowledgement (legacy behavior)
        self.assertTrue(sent.called)

    @mock.patch("pages.TelegramAPI.forwardMessage")
    @mock.patch("pages.TelegramAPI.sentMessage")
    def test_throttle_sends_client_only(self, sent, fwd):
        out = Outcome(action="throttle", client_text="Iltimos biroz kuting 🙏")
        private_ai.deliver(out, self.user, "spam", 90, self.conv)
        sent.assert_called_once_with("Message", self.user.user_id, "Iltimos biroz kuting 🙏")
        fwd.assert_not_called()

    @mock.patch("pages.TelegramAPI.forwardMessage", return_value={"result": {"message_id": 1}})
    @mock.patch("pages.TelegramAPI.sentMessage")
    def test_skip_handoff_forwards_only_no_ack(self, sent, fwd):
        out = Outcome(action="skip", reason="handoff")
        private_ai.deliver(out, self.user, "msg", 91, self.conv)
        fwd.assert_called_once_with(-100, self.user.user_id, 91)
        sent.assert_not_called()

    @mock.patch("pages.TelegramAPI.sendMessageReply")
    @mock.patch("pages.TelegramAPI.forwardMessage", return_value={"result": {"message_id": 1}})
    @mock.patch("pages.TelegramAPI.sentMessage")
    def test_complaint_pings_notify_user(self, sent, fwd, reply):
        s = AISettings.get(); s.complaint_notify_user_id = 999; s.save()
        out = Outcome(action="notify", client_text="Uzr", intent="complaint",
                      confidence=0.9, group_label="⚠️ SHIKOYAT", notify=True, set_handoff=True)
        private_ai.deliver(out, self.user, "yomon", 92, self.conv)
        self.assertTrue(any(c.args[1] == 999 for c in sent.call_args_list))

    @mock.patch("pages.TelegramAPI.sendMessageReply")
    @mock.patch("pages.TelegramAPI.forwardMessage", return_value={})
    @mock.patch("pages.TelegramAPI.sentMessage")
    def test_standalone_card_when_no_forward_id(self, sent, fwd, reply):
        out = Outcome(action="answer", client_text="javob", intent="info_question",
                      confidence=0.9, group_label="🤖 AI")
        private_ai.deliver(out, self.user, "q", 93, self.conv)
        reply.assert_not_called()
        self.assertTrue(any(c.args[1] == -100 for c in sent.call_args_list))

    @mock.patch("pages.TelegramAPI.sendMessageReply")
    @mock.patch("pages.TelegramAPI.forwardMessage")
    @mock.patch("pages.TelegramAPI.sentMessage")
    def test_no_active_group_still_replies(self, sent, fwd, reply):
        from pages.models import GroupBot
        GroupBot.objects.update(is_active=False)
        out = Outcome(action="answer", client_text="javob", intent="info_question",
                      confidence=0.9, group_label="🤖 AI")
        private_ai.deliver(out, self.user, "q", 94, self.conv)
        sent.assert_any_call("Message", self.user.user_id, "javob")
        fwd.assert_not_called()
