from django.db import transaction
from commercial_store.models import Journal, Outbox, ActorRef


@transaction.atomic
def record(
    action,
    *,
    actor=None,
    organization_id=None,
    target_id=None,
    result="success",
    request=None
):
    if actor and actor.is_authenticated:
        ActorRef.objects.get_or_create(
            pk=actor.pk, defaults={"username": actor.username}
        )
    values = dict(
        action=action,
        actor_id=actor.pk if actor and actor.is_authenticated else None,
        organization_id=organization_id,
        target_id=target_id,
        result=result,
    )
    if request is not None and hasattr(request, "request_id"):
        values["request_id"] = request.request_id
    event = Journal.objects.create(**values)
    Outbox.objects.create(event=event)
    return event
