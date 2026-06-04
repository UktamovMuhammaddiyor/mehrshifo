def process_client_message(user_id, text, message_id):
    """Django-Q job: run the AI pipeline for one customer message and deliver it."""
    from .models import BotUser, Conversation, ConversationMessage
    from .ai import pipeline
    from .handlers import private_ai

    try:
        user = BotUser.objects.get(user_id=user_id)
    except BotUser.DoesNotExist:
        return

    conversation = Conversation.active_for(user)
    ConversationMessage.objects.create(
        conversation=conversation, role="client", text=text, tg_message_id=message_id
    )
    outcome = pipeline.run(conversation, user, text)
    private_ai.deliver(outcome, user, text, message_id, conversation)
