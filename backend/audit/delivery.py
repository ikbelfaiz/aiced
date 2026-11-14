"""At-least-once delivery. No HTTP runs in the business transaction."""

import hashlib
import json
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException
from .models import AuditOutbox, AuditReceipt


from core.audit_envelope import envelope


@transaction.atomic
def receive(producer, payload):
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    receipt, created = AuditReceipt.objects.get_or_create(
        producer=producer,
        event_id=payload["event_id"],
        defaults={"digest": digest, "payload": payload},
    )
    if receipt.digest != digest:
        error = APIException("Événement audit contradictoire.")
        error.status_code = 409
        raise error
    return {"accepted": True, "event_id": str(receipt.event_id)}


def deliver(event_id, client):
    from django.db import connection

    if connection.in_atomic_block:
        raise RuntimeError(
            "Audit HTTP delivery must run outside the business transaction"
        )
    # Claim is deliberately replayable: concurrent workers may send twice, but
    # receiver deduplicates. A crash after acceptance before mark is harmless.
    row = AuditOutbox.objects.select_related("event").get(event_id=event_id)
    if row.delivered_at:
        return
    from django.db.models import F

    AuditOutbox.objects.filter(pk=event_id).update(attempts=F("attempts") + 1)
    payload = envelope(row.event)
    result = client.post("/internal/v1/audit/events", payload)
    if result.get("accepted") is not True or result.get("event_id") != str(event_id):
        raise RuntimeError("Audit delivery acknowledgment mismatch")
    AuditOutbox.objects.filter(pk=event_id, delivered_at__isnull=True).update(
        delivered_at=timezone.now()
    )
