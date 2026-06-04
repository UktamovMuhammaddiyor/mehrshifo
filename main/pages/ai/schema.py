INTENTS = [
    "greeting",
    "info_question",
    "complaint",
    "suggestion",
    "personal_data_request",
    "medical_advice_request",
    "appointment_request",
    "unclear",
]

AI_RESPONSE_SCHEMA = {
    "name": "support_reply",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reply_uz": {"type": "string"},
            "intent": {"type": "string", "enum": INTENTS},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "needs_human": {"type": "boolean"},
            "notify_admin": {"type": "boolean"},
        },
        "required": ["reply_uz", "intent", "confidence", "needs_human", "notify_admin"],
    },
}


def coerce_response(data: dict) -> dict:
    """Validate/normalize the model output into safe Python types."""
    intent = data.get("intent")
    if intent not in INTENTS:
        intent = "unclear"
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return {
        "reply_uz": str(data.get("reply_uz") or ""),
        "intent": intent,
        "confidence": confidence,
        "needs_human": bool(data.get("needs_human", False)),
        "notify_admin": bool(data.get("notify_admin", False)),
    }
