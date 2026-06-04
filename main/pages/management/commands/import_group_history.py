import json

from django.core.management.base import BaseCommand, CommandError

from pages.models import FAQSuggestion


def _flatten_text(text):
    """Telegram export 'text' is a string or a list of strings/entity dicts."""
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        parts = []
        for chunk in text:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict):
                parts.append(chunk.get("text", ""))
        return "".join(parts)
    return ""


class Command(BaseCommand):
    help = "Import a Telegram Desktop JSON export; reply-pairs become pending FAQ suggestions."

    def add_arguments(self, parser):
        parser.add_argument("json_path")

    def handle(self, *args, **options):
        try:
            with open(options["json_path"], encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Cannot read export: {exc}")

        messages = data.get("messages", [])
        by_id = {m.get("id"): m for m in messages if "id" in m}
        created = 0
        for m in messages:
            parent_id = m.get("reply_to_message_id")
            if parent_id is None or parent_id not in by_id:
                continue
            question = _flatten_text(by_id[parent_id].get("text", "")).strip()
            answer = _flatten_text(m.get("text", "")).strip()
            if not question or not answer:
                continue
            _, was_created = FAQSuggestion.objects.get_or_create(
                question=question, answer=answer, defaults={"status": "pending"}
            )
            created += int(was_created)
        self.stdout.write(f"Created {created} pending FAQ suggestion(s).")
