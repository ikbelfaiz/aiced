"""Replayable delivery outside business transactions; IAM deduplicates receipts."""

from django.db import connection
from django.db.models import F
from django.conf import settings
from django.utils import timezone
from internal_api.client import InternalClient
from core.audit_envelope import envelope
from commercial_store.models import Outbox


def deliver(event_id):
    if connection.in_atomic_block:
        raise RuntimeError("Audit delivery must run outside a business transaction")
    row = Outbox.objects.select_related("event").get(pk=event_id)
    if row.delivered_at:
        return
    Outbox.objects.filter(pk=event_id).update(attempts=F("attempts") + 1)
    key = settings.COMMERCIAL_IAM_KEY_ID
    client = InternalClient(
        settings.IAM_URL, key, settings.AICED_INTERNAL_KEYS[key]["secret"], "audit"
    )
    result = client.post("/internal/v1/audit/events", envelope(row.event))
    if result.get("accepted") is not True or result.get("event_id") != str(event_id):
        raise RuntimeError("Audit acknowledgment mismatch")
    Outbox.objects.filter(pk=event_id, delivered_at__isnull=True).update(
        delivered_at=timezone.now()
    )
