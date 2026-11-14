"""Minimal cross-service audit contract; never includes business context."""


def envelope(event):
    # Deliberately omit context: it can contain notes, grants or personal data.
    return {
        "event_id": str(event.pk),
        "occurred_at": event.occurred_at.isoformat(),
        "actor_id": str(event.actor_id) if event.actor_id else None,
        "organization_id": (
            str(event.organization_id) if event.organization_id else None
        ),
        "target_id": str(event.target_id) if event.target_id else None,
        "request_id": str(event.request_id),
        "action": event.action,
        "result": event.result,
    }
