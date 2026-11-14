from django.db import transaction
from .models import AuditEvent, AuditOutbox


@transaction.atomic
def record(action, *, actor=None, organization_id=None, target_id=None, result='success', request=None, context=None):
    values = dict(action=action, actor=actor if actor and actor.is_authenticated else None,
                  organization_id=organization_id, target_id=target_id, result=result, context=context or {})
    if request is not None and hasattr(request, 'request_id'):
        values['request_id'] = request.request_id
    event = AuditEvent.objects.create(**values)
    producer = ('integration' if action.startswith('imports.') else
                'commercial' if action.startswith('clients.opportunities') else
                'client_crm' if action.startswith(('clients.','prospects.')) else 'iam')
    AuditOutbox.objects.create(event=event,producer=producer)
    return event
