from django.db import transaction
from integration_store.models import Journal, Outbox


@transaction.atomic
def record(
    action,
    *,
    actor=None,
    organization_id=None,
    target_id=None,
    result="success",
    request=None,
    context=None
):
    event = Journal.objects.create(
        action=action,
        actor_id=actor.pk if actor and actor.is_authenticated else None,
        organization_id=organization_id,
        target_id=target_id,
        result=result,
        context=context or {},
        **(
            {"request_id": request.request_id}
            if request and hasattr(request, "request_id")
            else {}
        )
    )
    Outbox.objects.create(event=event)
    return event
