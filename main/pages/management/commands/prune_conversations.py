from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from pages.models import ConversationMessage


class Command(BaseCommand):
    help = "Delete ConversationMessages older than N days (privacy retention)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90)

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options["days"])
        deleted, _ = ConversationMessage.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f"Deleted {deleted} old conversation messages.")
