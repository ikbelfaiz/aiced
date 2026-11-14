from identity.coordination import admit
from django.db import transaction
from django.shortcuts import get_object_or_404
from audit.services import record
from .policies import client_queryset
from iam_consumer.compat import Organization
from .models import CRMProfile
from .serializers import CRMUpdateSerializer


@transaction.atomic
def update_crm(actor, party_id, data, request=None):
    visible = client_queryset(actor, 'clients.view')
    writable = client_queryset(actor, 'clients.update_crm').filter(pk__in=visible.values('pk'))
    candidate = get_object_or_404(writable, pk=party_id)
    # Use the same lock as role/membership mutations. Rebuild the authorization
    # query after waiting: READ COMMITTED must see any intervening revocation.
    Organization.objects.select_for_update().get(pk=candidate.organization_id)
    admit(actor, request)
    visible = client_queryset(actor, 'clients.view')
    writable = client_queryset(actor, 'clients.update_crm').filter(pk__in=visible.values('pk'))
    party = get_object_or_404(writable.select_for_update(of=('self',)), pk=party_id)
    serializer = CRMUpdateSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    profile, _ = CRMProfile.objects.get_or_create(party=party)
    profile.notes = serializer.validated_data['notes']
    profile.version += 1
    profile.updated_by = actor
    profile.save()
    record('clients.crm_updated', actor=actor, organization_id=party.organization_id,
           target_id=party.pk, request=request)
    return profile
