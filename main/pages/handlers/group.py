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
    return True
