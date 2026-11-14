"""Client-owned object scoping. IAM supplies grants, never client queries."""

from django.db.models import Q
from identity.policies import grants, organization_ids
from django.conf import settings
from .models import Party


def client_queryset(user, code):
    if getattr(settings, 'IAM_REMOTE', False):
        from iam_consumer.access import scope
        full, assigned = scope(user, code)
        prospect_full, prospect_assigned = scope(user, 'prospects.view')
        return Party.objects.filter(Q(organization_id__in=full) | Q(assigned_to_id__in=assigned)).filter(Q(prospect__isnull=True) | Q(organization_id__in=prospect_full) | Q(assigned_to_id__in=prospect_assigned))
    full = organization_ids(user, code, full_scope=True)
    assigned = (
        grants(user, code)
        .filter(scope="assigned")
        .values("membership_id")
    )
    queryset = Party.objects.filter(
        Q(organization_id__in=full) | Q(assigned_to_id__in=assigned)
    ).filter(organization__is_active=True)
    # Apply prospect visibility on every legacy and workspace route, not just its list.
    prospect_full = organization_ids(user, "prospects.view", full_scope=True)
    prospect_assigned = (
        grants(user, "prospects.view")
        .filter(scope="assigned")
        .values("membership_id")
    )
    return queryset.filter(
        Q(prospect__isnull=True)
        | Q(organization_id__in=prospect_full)
        | Q(assigned_to_id__in=prospect_assigned)
    )
