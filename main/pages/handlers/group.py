EXCLUDED_INTENTS = {"personal_data_request", "medical_advice_request"}


def _maybe_capture_suggestion(target_user_id, answer_text):
    """Capture (last customer question, staff answer) as a pending FAQ suggestion,
    unless the latest escalation was personal/medical (privacy)."""
    from ..models import BotUser, Conversation, ConversationMessage, AIDecisionLog, FAQSuggestion
    answer_text = (answer_text or "").strip()
    if not answer_text:
        return
    try:
        user = BotUser.objects.get(user_id=target_user_id)
    except BotUser.DoesNotExist:
        return
    conv = Conversation.active_for(user)
    last_decision = AIDecisionLog.objects.filter(conversation=conv).order_by("-id").first()
    if last_decision and last_decision.intent in EXCLUDED_INTENTS:
        return
    question = (
        ConversationMessage.objects.filter(conversation=conv, role="client")
        .order_by("-id").values_list("text", flat=True).first()
    )
    if not question:
        return
    FAQSuggestion.objects.get_or_create(
        question=question, answer=answer_text,
        defaults={"source_conversation": conv, "status": "pending"},
    )


def _set_status(target_user_id, status):
    from ..models import BotUser, Conversation
    try:
        user = BotUser.objects.get(user_id=target_user_id)
    except BotUser.DoesNotExist:
        return
    conv = Conversation.active_for(user)
    if conv.status != status:
        conv.status = status
        conv.save(update_fields=["status"])


def handle_group_message(response) -> bool:
    """Handle a staff reply to a bot-forwarded customer message.

    Returns True if it acted (relayed a reply or resumed AI), else False.
    """
    reply_to = response.get("reply_to_message")
    if not reply_to:
        return False
    if not (reply_to.get("from", {}).get("is_bot") and "forward_origin" in reply_to):
        return False
    origin = reply_to["forward_origin"]
    if "sender_user" not in origin:   # forward-privacy hides the id → cannot route back
        return False
    target_user_id = origin["sender_user"]["id"]

    if (response.get("text") or "").strip() == "/ai_resume":
        _set_status(target_user_id, "active")
        return True

    from ..TelegramAPI import copyMessage
    copyMessage(target_user_id, response["chat"]["id"], response["message_id"])
    _set_status(target_user_id, "handoff")
    _maybe_capture_suggestion(target_user_id, response.get("text") or response.get("caption"))
    return True
