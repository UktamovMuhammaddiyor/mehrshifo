def _card(outcome) -> str:
    from ..TelegramAPI import escape_html
    if outcome.action == "answer":
        return f"🤖 AI javob berdi:\n{escape_html(outcome.client_text)}"
    if outcome.action == "notify":
        return f"{outcome.group_label}\n🤖 AI: {escape_html(outcome.client_text)}"
    return outcome.group_label  # escalate


def _notify_complaint(user, outcome):
    from ..models import AISettings
    from ..TelegramAPI import sentMessage, escape_html
    settings = AISettings.get()
    if settings.complaint_notify_user_id:
        text = f"{outcome.group_label}\nMijoz: {escape_html(user.name)} (id {user.user_id})"
        sentMessage("Message", settings.complaint_notify_user_id, text)


def _log(conversation, incoming_text, outcome):
    from ..models import AIDecisionLog
    from ..knowledge.snapshot import kb_version
    AIDecisionLog.objects.create(
        conversation=conversation, input_text=incoming_text, kb_version=kb_version(),
        intent=outcome.intent, confidence=outcome.confidence,
        action=outcome.action, output_text=outcome.client_text,
    )


def deliver(outcome, user, incoming_text, client_message_id, conversation):
    from ..models import GroupBot, AutoAnswer, ConversationMessage
    from ..TelegramAPI import sentMessage, forwardMessage, sendMessageReply

    group = GroupBot.objects.filter(is_active=True).first()

    if outcome.action == "throttle":
        if outcome.client_text:
            sentMessage("Message", user.user_id, outcome.client_text)
        _log(conversation, incoming_text, outcome)
        return

    if outcome.action == "skip":
        # AI off / handoff / daily cap → legacy "forward to group" behavior
        if outcome.reason == "ai_disabled":
            ans = AutoAnswer.objects.first()
            sentMessage("Message", user.user_id,
                        ans.text if ans else "Murojatingiz qabul qilindi.")
        if group:
            forwardMessage(group.group_id, user.user_id, client_message_id)
        _log(conversation, incoming_text, outcome)
        return

    # answer | notify | escalate
    if outcome.client_text:
        sentMessage("Message", user.user_id, outcome.client_text)
    if group:
        fwd = forwardMessage(group.group_id, user.user_id, client_message_id)
        fwd_mid = (fwd or {}).get("result", {}).get("message_id")
        card = _card(outcome)
        if fwd_mid:
            sendMessageReply(group.group_id, card, fwd_mid)
        else:
            sentMessage("Message", group.group_id, card)
        if outcome.notify:
            _notify_complaint(user, outcome)

    if outcome.set_handoff and conversation.status != "handoff":
        conversation.status = "handoff"
        conversation.save(update_fields=["status"])

    ConversationMessage.objects.create(
        conversation=conversation, role="ai", text=outcome.client_text,
        intent=outcome.intent, confidence=outcome.confidence,
    )
    _log(conversation, incoming_text, outcome)
