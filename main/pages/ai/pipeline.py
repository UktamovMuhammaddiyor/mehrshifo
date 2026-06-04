import time
from dataclasses import dataclass

from django.core.cache import cache

ESCALATE_INTENTS = {"personal_data_request", "medical_advice_request"}


@dataclass
class Outcome:
    action: str            # answer | notify | escalate | skip | throttle
    client_text: str = ""  # text to send the client ("" = nothing)
    group_label: str = ""  # header for the group card ("" = no card)
    intent: str = ""
    confidence: float = 0.0
    notify: bool = False       # ping complaint recipient
    set_handoff: bool = False  # pause AI for this conversation
    reason: str = ""


def _rate_limited(user_id, limit=8, window=60) -> bool:
    key = f"rl:{user_id}:{int(time.time()) // window}"
    count = (cache.get(key) or 0) + 1
    cache.set(key, count, window)
    return count > limit


def _daily_key() -> str:
    return "ai_calls:" + time.strftime("%Y%m%d", time.gmtime())


def _over_daily_cap(settings) -> bool:
    return (cache.get(_daily_key()) or 0) >= settings.daily_call_cap


def _incr_daily() -> None:
    key = _daily_key()
    cache.set(key, (cache.get(key) or 0) + 1, 60 * 60 * 26)


def decide_action(parsed: dict, settings) -> Outcome:
    intent = parsed["intent"]
    conf = parsed["confidence"]
    reply = parsed["reply_uz"]
    notify = bool(parsed["notify_admin"]) or intent in {"complaint", "suggestion"}

    if intent in ESCALATE_INTENTS or parsed["needs_human"] or conf < settings.confidence_threshold:
        label = "🔔 AI javob bera olmadi — hodim javob bersin"
        if intent == "personal_data_request":
            label = "🔔 Shaxsiy ma'lumot so'rovi — hodim javob bersin"
        elif intent == "medical_advice_request":
            label = "🔔 Tibbiy maslahat so'rovi — hodim javob bersin"
        reason = ("escalate_intent" if intent in ESCALATE_INTENTS
                  else "needs_human" if parsed["needs_human"] else "low_confidence")
        return Outcome(action="escalate", client_text=settings.holding_message,
                       group_label=label, intent=intent, confidence=conf, reason=reason)

    if intent == "complaint":
        return Outcome(action="notify", client_text=reply, group_label="⚠️ SHIKOYAT",
                       intent=intent, confidence=conf, notify=True, set_handoff=True,
                       reason="complaint")
    if intent == "suggestion":
        return Outcome(action="notify", client_text=reply, group_label="💡 TAKLIF",
                       intent=intent, confidence=conf, notify=True, reason="suggestion")

    return Outcome(action="answer", client_text=reply, group_label="🤖 AI",
                   intent=intent, confidence=conf, notify=notify, reason="answer")


def run(conversation, user, text, client=None) -> Outcome:
    from ..models import AISettings
    from .schema import AI_RESPONSE_SCHEMA
    from .prompts import build_system_prompt, build_messages
    from .guardrails import truncate_input, check_output
    from ..knowledge.snapshot import get_kb_snapshot
    from .client import OpenAIClient

    settings = AISettings.get()
    if not settings.is_enabled:
        return Outcome(action="skip", reason="ai_disabled")
    if conversation.status == "handoff":
        return Outcome(action="skip", reason="handoff")
    if _rate_limited(user.user_id):
        return Outcome(action="throttle", client_text="Iltimos biroz kuting 🙏",
                       reason="rate_limited")
    if _over_daily_cap(settings):
        return Outcome(action="skip", reason="daily_cap")

    text = truncate_input(text, settings.max_input_chars)
    system = build_system_prompt(get_kb_snapshot(), settings)
    history = list(conversation.messages.order_by("-id")[: settings.max_history_messages])[::-1]
    messages = build_messages(history, text)

    if client is None:
        client = OpenAIClient(settings.model_name, settings.temperature, settings.max_output_tokens)
    _incr_daily()
    try:
        parsed = client.complete(system, messages, AI_RESPONSE_SCHEMA)
    except Exception:
        # LLM/network failure must never drop the customer — escalate to staff.
        return Outcome(action="escalate", client_text=settings.holding_message,
                       group_label="🔔 AI xatosi — hodim javob bersin",
                       intent="unclear", reason="llm_error")

    ok, _reason = check_output(parsed["reply_uz"])
    if not ok:
        return Outcome(action="escalate", client_text=settings.holding_message,
                       group_label="🔔 AI javob bera olmadi (guardrail)",
                       intent=parsed["intent"], confidence=parsed["confidence"],
                       reason="guardrail_block")

    return decide_action(parsed, settings)
