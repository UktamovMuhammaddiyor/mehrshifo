import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


def validate_init_data(raw_init_data, max_age_seconds=86400):
    """Return the Telegram user dict if initData HMAC is valid + fresh, else None."""
    from ..creditionals import BOT_TOKEN
    if not raw_init_data:
        return None
    if not BOT_TOKEN:
        return None
    pairs = dict(parse_qsl(raw_init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    if max_age_seconds and (time.time() - auth_date) > max_age_seconds:
        return None
    try:
        parsed = json.loads(pairs.get("user") or "")
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def is_allowed(user):
    """Fail-closed staff gate: empty allowlist denies everyone."""
    from ..creditionals import ADMIN_USER_IDS
    return isinstance(user, dict) and bool(ADMIN_USER_IDS) and user.get("id") in ADMIN_USER_IDS
