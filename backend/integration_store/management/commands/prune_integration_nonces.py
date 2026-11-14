from django.core.management.base import BaseCommand
from django.utils import timezone
from integration_store.models import InternalNonce


class Command(BaseCommand):
    help = "Prune only expired Integration replay digests; never domain/audit history."

    def handle(self, *args, **options):
        count, _ = InternalNonce.objects.filter(expires_at__lt=timezone.now()).delete()
        self.stdout.write(f"Expired replay digests removed: {count}")
