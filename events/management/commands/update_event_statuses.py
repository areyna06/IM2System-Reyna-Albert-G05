from django.core.management.base import BaseCommand

from events.models import sync_event_statuses


class Command(BaseCommand):
    help = "Close events past their registration deadline and complete events that have ended."

    def handle(self, *args, **options):
        closed, completed = sync_event_statuses()
        self.stdout.write(self.style.SUCCESS(f"{closed} event(s) closed, {completed} event(s) completed."))
