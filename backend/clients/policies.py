"""Client-owned object scoping. IAM supplies grants, never client queries."""

from django.db.models import Q
from identity.policies import grants, organization_ids
from identity.models import RoleAssignment
from .models import Party


def client_queryset(user, code):
    full = organization_ids(user, code, full_scope=True)
    assigned = (
        grants(user, code)
        .filter(scope=RoleAssignment.Scope.ASSIGNED)
        .values("membership_id")
    )
    queryset = Party.objects.filter(
        Q(organization_id__in=full) | Q(assigned_to_id__in=assigned)
    ).filter(organization__is_active=True)
    # Apply prospect visibility on every legacy and workspace route, not just its list.
    prospect_full = organization_ids(user, "prospects.view", full_scope=True)
    prospect_assigned = (
        grants(user, "prospects.view")
        .filter(scope=RoleAssignment.Scope.ASSIGNED)
        .values("membership_id")
    )
    return queryset.filter(
        Q(prospect__isnull=True)
        | Q(organization_id__in=prospect_full)
        | Q(assigned_to_id__in=prospect_assigned)
    )
