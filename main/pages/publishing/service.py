from ..models import ContentDraft
from .publishers import WordPressPublisher, ChannelPublisher, BotUsersPublisher

PUBLISHERS = {
    "site": WordPressPublisher,
    "channel": ChannelPublisher,
    "bot_users": BotUsersPublisher,
}


def start_generation(created_by, kind, title, reference_link=""):
    draft = ContentDraft.objects.create(
        created_by=created_by, kind=kind, mode="ai", title=title,
        reference_link=reference_link or "", status="generating",
    )
    from django_q.tasks import async_task
    async_task("pages.tasks.generate_content_job", draft.id)
    return draft


def run_generation(draft_id):
    from ..knowledge.snapshot import get_kb_snapshot
    from .generator import generate_content
    try:
        draft = ContentDraft.objects.get(id=draft_id)
    except ContentDraft.DoesNotExist:
        return
    try:
        result = generate_content(draft.kind, draft.title, draft.reference_link, get_kb_snapshot())
        draft.body = result["body"]
        draft.status = "ready"
        draft.save(update_fields=["body", "status", "updated_at"])
    except Exception as exc:
        draft.status = "failed"
        draft.error = str(exc)
        draft.save(update_fields=["status", "error", "updated_at"])


def publish_draft(draft, targets):
    results = {}
    any_ok = False
    for key, want in (targets or {}).items():
        if not want or key not in PUBLISHERS:
            continue
        res = PUBLISHERS[key]().publish(draft)
        results[key] = res
        any_ok = any_ok or bool(res.get("ok"))
    draft.targets = targets or {}
    draft.publish_results = results
    draft.status = "published" if any_ok else "failed"
    draft.save(update_fields=["targets", "publish_results", "status", "updated_at"])
    return results
