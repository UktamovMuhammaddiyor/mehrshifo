SUSPICIOUS_OUTPUT_MARKERS = [
    "system prompt",
    "begin system",
    "openai_api_key",
    "ignore previous",
    "qoidalaringni",
]


def truncate_input(text: str, max_chars: int) -> str:
    return (text or "").strip()[:max_chars]


def check_output(text: str) -> tuple[bool, str]:
    low = (text or "").lower()
    for marker in SUSPICIOUS_OUTPUT_MARKERS:
        if marker in low:
            return False, f"blocked marker: {marker}"
    if len(text or "") > 4000:
        return False, "too long"
    return True, ""
