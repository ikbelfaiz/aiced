from django.core.management.base import BaseCommand, CommandError
from commercial_store.models import Outbox
from commercial_service.delivery import deliver


class Command(BaseCommand):
    help = "Deliver a bounded batch of owned audit outboxes using the scoped machine identity."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 100:
            raise CommandError("Limit must be between 1 and 100")
        for ident in (
            Outbox.objects.filter(delivered_at__isnull=True)
            .order_by("created_at")
            .values_list("event_id", flat=True)[:limit]
        ):
            deliver(ident)
        self.stdout.write("Commercial audit batch completed.")
