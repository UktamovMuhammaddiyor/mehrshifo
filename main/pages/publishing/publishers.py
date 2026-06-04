import base64

import requests

from ..TelegramAPI import sentMessage
from ..models import BotUser, ChannelBot


def _telegram_text(draft):
    return f"<b>{draft.title}</b>\n\n{draft.body}" if draft.title else draft.body


class WordPressPublisher:
    def publish(self, draft):
        from ..creditionals import WORDPRESS_URL, WORDPRESS_USER, WORDPRESS_APP_PASSWORD
        url = WORDPRESS_URL.rstrip("/") + "/wp-json/wp/v2/posts"
        token = base64.b64encode(
            f"{WORDPRESS_USER}:{WORDPRESS_APP_PASSWORD}".encode()
        ).decode()
        try:
            resp = requests.post(
                url,
                headers={"Authorization": f"Basic {token}"},
                json={"title": draft.title, "content": draft.body, "status": "publish"},
                timeout=30,
            )
            data = resp.json()
            if resp.status_code in (200, 201) and "link" in data:
                return {"ok": True, "url": data["link"]}
            return {"ok": False, "error": data.get("message", f"HTTP {resp.status_code}")}
        except Exception as exc:  # network/parse errors must not crash publishing
            return {"ok": False, "error": str(exc)}


class ChannelPublisher:
    def publish(self, draft):
        channel = ChannelBot.objects.first()
        if not channel:
            return {"ok": False, "error": "no channel registered"}
        res = sentMessage("Message", channel.chat_id, _telegram_text(draft))
        if isinstance(res, dict) and res.get("ok"):
            return {"ok": True, "message_id": res["result"]["message_id"]}
        return {"ok": False, "error": (res or {}).get("description", "send failed")}


class BotUsersPublisher:
    def publish(self, draft):
        text = _telegram_text(draft)
        count = 0
        for user in BotUser.objects.all():
            res = sentMessage("Message", user.user_id, text)
            if isinstance(res, dict) and res.get("ok"):
                count += 1
        return {"ok": True, "count": count}
