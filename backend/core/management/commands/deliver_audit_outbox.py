from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from audit.delivery import deliver
from audit.models import AuditOutbox
from internal_api.client import InternalClient


class Command(BaseCommand):
    help = "Deliver one bounded batch; failures remain pending for a later replay."

    def add_arguments(self, parser):
        parser.add_argument("--endpoint", required=True)
        parser.add_argument("--key-id", required=True)
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        key = settings.AICED_INTERNAL_KEYS.get(options["key_id"])
        if (
            not key
            or "audit" not in key["audiences"]
            or not 1 <= options["limit"] <= 1000
        ):
            raise CommandError("Invalid audit key or batch limit")
        client = InternalClient(
            options["endpoint"], options["key_id"], key["secret"], "audit"
        )
        ids = list(
            AuditOutbox.objects.filter(
                delivered_at__isnull=True, producer=key["service"]
            )
            .order_by("created_at")
            .values_list("event_id", flat=True)[: options["limit"]]
        )
        failed = 0
        for event_id in ids:
            try:
                deliver(event_id, client)
            except Exception:
                failed += 1
        self.stdout.write(
            f"Audit delivered: {len(ids)-failed}; pending failures: {failed}"
        )
        if failed:
            raise CommandError("Some audit deliveries remain pending")
