from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from .models import RoleAssignment


def grants(user, code=None):
    from django.conf import settings
    if getattr(settings, 'IAM_REMOTE', False):
        from iam_consumer.access import grant_rows
        return grant_rows(user, code)
    if not user.is_authenticated or not user.is_active:
        return RoleAssignment.objects.none()
    qs = RoleAssignment.objects.filter(
        membership__user=user, membership__user__is_active=True, membership__is_active=True,
        membership__organization__is_active=True, role__is_active=True, is_active=True,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
    return qs.filter(role__permissions__code=code) if code else qs


def organization_ids(user, code, full_scope=False):
    from django.conf import settings
    if getattr(settings, 'IAM_REMOTE', False):
        from iam_consumer.access import organization_values
        return organization_values(user, code, full_scope)
    qs = grants(user, code)
    if full_scope:
        qs = qs.filter(scope=RoleAssignment.Scope.ORGANIZATION)
    return qs.values_list('membership__organization_id', flat=True)


def require(user, code, organization_id, full_scope=False):
    if not organization_ids(user, code, full_scope).filter(
        membership__organization_id=organization_id
    ).exists():
        raise PermissionDenied('Opération non autorisée.')


def can_delegate(user, role, organization_id):
    require(user, 'users.manage', organization_id, full_scope=True)
    # Vacuous empty roles are harmless, but disabled roles cannot be delegated.
    if not role.is_active:
        return False
    # Assigned scope is principal-relative. Delegating it to another principal
    # could expose a portfolio the actor cannot read, so require organization
    # authority for every delegated capability, even for an assigned grant.
    actor = grants(user).filter(membership__organization_id=organization_id,
                                scope=RoleAssignment.Scope.ORGANIZATION)
    codes = set(actor.values_list('role__permissions__code', flat=True))
    return set(role.permissions.values_list('code', flat=True)) <= codes
