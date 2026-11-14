from identity.coordination import admit
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from audit.services import record
from .models import Membership, Role, RoleAssignment, User
from .policies import can_delegate, require
from .serializers import GrantSerializer, CreateUserSerializer, MembershipStateSerializer


def assignment_snapshot(assignment):
    return {'membership_id': str(assignment.membership_id), 'role_id': str(assignment.role_id),
            'permissions': sorted(assignment.role.permissions.values_list('code', flat=True)),
            'scope': assignment.scope, 'is_active': assignment.is_active,
            'expires_at': assignment.expires_at.isoformat() if assignment.expires_at else None}


def require_delegation_duration(actor, role, organization_id, expires_at):
    from .policies import grants
    from django.db.models import Q
    needed = set(role.permissions.values_list('code', flat=True)) | {'users.manage'}
    for code in needed:
        authority = grants(actor, code).filter(membership__organization_id=organization_id,
                                               scope=RoleAssignment.Scope.ORGANIZATION)
        if expires_at is None:
            authority = authority.filter(expires_at__isnull=True)
        else:
            authority = authority.filter(Q(expires_at__isnull=True) | Q(expires_at__gte=expires_at))
        if not authority.exists():
            raise PermissionDenied('La délégation ne peut dépasser la durée de votre habilitation.')


@transaction.atomic
def assign_role(actor, organization_id, data, request=None):
    require(actor, 'users.manage', organization_id, full_scope=True)
    serializer = GrantSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    # Serialize administrative changes within an organization, including revocation.
    from .models import Organization
    Organization.objects.select_for_update().get(pk=organization_id)
    admit(actor, request, exclusive=True)
    require(actor, 'users.manage', organization_id, full_scope=True)
    target = get_object_or_404(Membership.objects.select_for_update(),
                               pk=data['membership_id'], organization_id=organization_id, is_active=True)
    if target.user_id == actor.pk:
        raise PermissionDenied('La modification de ses propres habilitations est interdite.')
    role = get_object_or_404(Role, pk=data['role_id'], is_active=True)
    if not can_delegate(actor, role, organization_id):
        raise PermissionDenied('Habilitation ou périmètre non délégable.')
    expires_at = data.get('expires_at')
    if expires_at and expires_at <= timezone.now():
        raise ValidationError({'expires_at': 'La date doit être future.'})
    # A temporary administrator must not create a grant outliving their authority.
    require_delegation_duration(actor, role, organization_id, expires_at)
    previous = RoleAssignment.objects.filter(membership=target, role=role, scope=data['scope']).first()
    before = assignment_snapshot(previous) if previous else None
    assignment, _ = RoleAssignment.objects.update_or_create(
        membership=target, role=role, scope=data['scope'],
        defaults={'expires_at': expires_at, 'is_active': True},
    )
    record('permissions.granted', actor=actor, organization_id=organization_id,
           target_id=assignment.pk, request=request, context={'before': before, 'after': assignment_snapshot(assignment)})
    return assignment


@transaction.atomic
def revoke_role(actor, organization_id, assignment_id, request=None):
    require(actor, 'users.manage', organization_id, full_scope=True)
    from .models import Organization
    Organization.objects.select_for_update().get(pk=organization_id)
    admit(actor, request, exclusive=True)
    require(actor, 'users.manage', organization_id, full_scope=True)
    assignment = get_object_or_404(RoleAssignment.objects.select_for_update(of=('self',)).select_related('membership', 'role'),
                                   pk=assignment_id, membership__organization_id=organization_id)
    effective = (assignment.is_active and assignment.role.is_active
                 and (assignment.expires_at is None or assignment.expires_at > timezone.now()))
    if assignment.membership.user_id == actor.pk or (effective and not can_delegate(actor, assignment.role, organization_id)):
        raise PermissionDenied('Modification non autorisée.')
    before = assignment_snapshot(assignment)
    assignment.is_active = False
    assignment.save(update_fields=['is_active'])
    record('permissions.revoked', actor=actor, organization_id=organization_id,
           target_id=assignment.pk, request=request, context={'before': before, 'after': assignment_snapshot(assignment)})


@transaction.atomic
def create_user(actor, organization_id, data, request=None):
    require(actor, 'users.manage', organization_id, full_scope=True)
    serializer = CreateUserSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    from .models import Organization
    Organization.objects.select_for_update().get(pk=organization_id)
    admit(actor, request, exclusive=True)
    require(actor, 'users.manage', organization_id, full_scope=True)
    user = User(username=data['username'])
    try:
        user.full_clean(exclude=['password'])
        validate_password(data['password'], user)
    except DjangoValidationError:
        raise ValidationError('Identifiant indisponible ou mot de passe non conforme.')
    user.set_password(data['password'])
    try:
        with transaction.atomic():
            user.save()
    except IntegrityError:
        raise ValidationError('Identifiant indisponible ou mot de passe non conforme.')
    membership = Membership.objects.create(user=user, organization_id=organization_id)
    record('users.created', actor=actor, organization_id=organization_id, target_id=user.pk, request=request)
    return membership


@transaction.atomic
def set_membership_state(actor, organization_id, membership_id, data, request=None):
    require(actor, 'users.manage', organization_id, full_scope=True)
    serializer = MembershipStateSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    is_active = serializer.validated_data['is_active']
    from .models import Organization
    Organization.objects.select_for_update().get(pk=organization_id)
    admit(actor, request, exclusive=True)
    require(actor, 'users.manage', organization_id, full_scope=True)
    target = get_object_or_404(Membership.objects.select_for_update(), pk=membership_id, organization_id=organization_id)
    if target.user_id == actor.pk:
        raise PermissionDenied('La modification de son propre accès est interdite.')
    for assignment in target.role_assignments.filter(is_active=True).select_related('role'):
        if not is_active and (not assignment.role.is_active or (
            assignment.expires_at is not None and assignment.expires_at <= timezone.now()
        )):
            # Removing access cannot resurrect an inactive/expired capability.
            continue
        if not can_delegate(actor, assignment.role, organization_id):
            raise PermissionDenied('Modification non autorisée.')
        if is_active:
            require_delegation_duration(actor, assignment.role, organization_id, assignment.expires_at)
    before = target.is_active
    target.is_active = is_active
    target.save(update_fields=['is_active'])
    record('membership.changed', actor=actor, organization_id=organization_id, target_id=target.pk, request=request,
           context={'before': {'is_active': before}, 'after': {'is_active': is_active}})
    return target


@transaction.atomic
def deactivate_user(actor, user_id, request=None):
    """Administrative Python boundary, no new public route or staff bypass."""
    admit(actor, request, exclusive=True)
    if str(actor.pk) == str(user_id):
        raise PermissionDenied('Auto-désactivation interdite.')
    target = get_object_or_404(User, pk=user_id)
    memberships = list(Membership.objects.filter(user=target))
    if not memberships:
        raise PermissionDenied('Périmètre utilisateur indisponible.')
    for member in memberships:
        require(actor,'users.manage',member.organization_id,full_scope=True)
        for assignment in member.role_assignments.filter(is_active=True).select_related('role'):
            if assignment.role.is_active and (assignment.expires_at is None or assignment.expires_at > timezone.now()):
                if not can_delegate(actor,assignment.role,member.organization_id):
                    raise PermissionDenied('Habilitation non délégable.')
    target.is_active = False
    target.save(update_fields=['is_active'])
    for member in memberships:
        record('users.deactivated',actor=actor,organization_id=member.organization_id,
               target_id=target.pk,request=request)
    return target
