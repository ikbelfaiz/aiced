"""S6 preparation: local adapter preserves existing locks and audit transaction.

This module deliberately uses the legacy local Opportunity model. It is NOT a
service boundary. Replace Client ORM authorization only after the cross-process
scope-fencing and restored-database rollback rehearsal have passed.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from audit.services import record
from .contracts import OpportunityInput


@transaction.atomic
def save_opportunity(actor, party_id, data, activity_id=None, request=None):
    # Lazy compatibility dependencies: contracts have no business-model imports.
    from clients.models import Opportunity
    from clients.workspace import accessible, check_version, validate

    party = accessible(
        actor, party_id, "opportunities.manage", lock=True, request=request
    )
    accessible(actor, party_id, "opportunities.view")
    values = validate(OpportunityInput, data, partial=activity_id is not None)
    if activity_id:
        item = get_object_or_404(
            Opportunity.objects.select_for_update(), pk=activity_id, party=party
        )
        check_version(item, values)
        for key, value in values.items():
            setattr(item, key, value)
        item.version += 1
        item.save()
    else:
        if "version" in values:
            raise serializers.ValidationError(
                "Version interdite \u00e0 la cr\u00e9ation."
            )
        item = Opportunity.objects.create(party=party, author=actor, **values)
    record(
        "clients.opportunities_saved",
        actor=actor,
        organization_id=party.organization_id,
        target_id=item.pk,
        request=request,
    )
    return item
