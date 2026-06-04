import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from ..publishing.auth import validate_init_data, is_allowed
from ..publishing.service import start_generation, publish_draft
from ..models import BotUser, ContentDraft


def _staff(request):
    """Validate initData + allowlist; return (or create) the staff BotUser, else None."""
    user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""))
    if not user or not is_allowed(user):
        return None
    botuser, _ = BotUser.objects.get_or_create(
        user_id=user["id"],
        defaults={"name": user.get("first_name", ""), "user_name": user.get("username", "")},
    )
    return botuser


def composer(request):
    """Serve the Mini App shell (public HTML; all actions are auth-gated via the API)."""
    return render(request, "miniapp/composer.html", {})


@csrf_exempt
def api_generate(request):
    staff = _staff(request)
    if not staff:
        return JsonResponse({"error": "forbidden"}, status=403)
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)
    draft = start_generation(staff, data.get("kind", "post"), data.get("title", ""),
                             data.get("reference_link", ""))
    return JsonResponse({"draft_id": draft.id, "status": draft.status})


@csrf_exempt
def api_draft(request, draft_id):
    staff = _staff(request)
    if not staff:
        return JsonResponse({"error": "forbidden"}, status=403)
    try:
        draft = ContentDraft.objects.get(id=draft_id)
    except ContentDraft.DoesNotExist:
        return JsonResponse({"error": "not found"}, status=404)
    return JsonResponse({"status": draft.status, "body": draft.body, "error": draft.error})


@csrf_exempt
def api_publish(request):
    staff = _staff(request)
    if not staff:
        return JsonResponse({"error": "forbidden"}, status=403)
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)
    draft_id = data.get("draft_id")
    if draft_id:
        try:
            draft = ContentDraft.objects.get(id=draft_id)
        except ContentDraft.DoesNotExist:
            return JsonResponse({"error": "not found"}, status=404)
        draft.title = data.get("title", draft.title)
        draft.body = data.get("body", draft.body)
        draft.save(update_fields=["title", "body", "updated_at"])
    else:
        draft = ContentDraft.objects.create(
            created_by=staff, kind=data.get("kind", "post"), mode="manual",
            title=data.get("title", ""), body=data.get("body", ""), status="draft",
        )
    results = publish_draft(draft, data.get("targets", {}))
    return JsonResponse({"status": draft.status, "results": results})
