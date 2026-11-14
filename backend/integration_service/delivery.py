"""Replayable local outbox; only delivery metadata can change."""

from django.db import connection
from django.db.models import F
from django.utils import timezone
from integration_store.models import Outbox
from .access import iam


def deliver(event_id):
    if connection.in_atomic_block:
        raise RuntimeError("HTTP delivery must run outside the business transaction")
    row = Outbox.objects.select_related("event").get(pk=event_id)
    if row.delivered_at:
        return
    Outbox.objects.filter(pk=event_id).update(attempts=F("attempts") + 1)
    event = row.event
    payload = {
        "event_id": str(event.pk),
        "occurred_at": event.occurred_at.isoformat(),
        "action": event.action,
        "result": event.result,
        **{
            field: str(getattr(event, field)) if getattr(event, field) else None
            for field in ("actor_id", "organization_id", "target_id", "request_id")
        },
    }
    result = iam("audit").post("/internal/v1/audit/events", payload)
    if result.get("accepted") is not True or result.get("event_id") != str(event_id):
        raise RuntimeError("Invalid audit acknowledgment")
    Outbox.objects.filter(pk=event_id, delivered_at__isnull=True).update(
        delivered_at=timezone.now()
    )
