from django.core.management.base import BaseCommand
from django.utils import timezone
from identity.models import InternalNonce


class Command(BaseCommand):
    help = (
        "Remove expired internal replay digests only (after their acceptance window)."
    )

    def handle(self, *args, **options):
        count, _ = InternalNonce.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(f"Expired internal nonce records removed: {count}")
