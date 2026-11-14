from django.core.management.base import BaseCommand, CommandError
from integration_store.models import Outbox
from integration_service.delivery import deliver


class Command(BaseCommand):
    help = "Deliver a bounded, retryable batch of local audit outbox entries."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 1000:
            raise CommandError("Limit must be 1..1000")
        failed = 0
        rows = list(
            Outbox.objects.filter(delivered_at__isnull=True)
            .order_by("event__occurred_at")
            .values_list("pk", flat=True)[: options["limit"]]
        )
        for pk in rows:
            try:
                deliver(pk)
            except Exception:
                failed += 1
        self.stdout.write(f"Delivered: {len(rows)-failed}; pending failures: {failed}")
        if failed:
            raise CommandError("Audit delivery incomplete; retry pending entries")
