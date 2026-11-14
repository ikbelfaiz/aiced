import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=160)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)


class Capability(models.Model):
    # Separate from Django's global permissions: no superuser or Group fallback.
    code = models.CharField(max_length=100, primary_key=True)
    description = models.CharField(max_length=200)


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    permissions = models.ManyToManyField(Capability, blank=True)
    is_active = models.BooleanField(default=True)


class Membership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'organization'], name='membership_user_org_unique'),
            models.UniqueConstraint(fields=['id', 'organization'], name='membership_id_org_unique'),
        ]


class RoleAssignment(models.Model):
    class Scope(models.TextChoices):
        ASSIGNED = 'assigned', 'Clients affectés'
        ORGANIZATION = 'organization', 'Organisation'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name='role_assignments')
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.ASSIGNED)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['membership', 'role', 'scope'], name='role_assignment_unique'),
            models.CheckConstraint(condition=models.Q(scope__in=['assigned', 'organization']), name='role_scope_valid'),
        ]


class LoginBucket(models.Model):
    # HMAC keys only: never persist submitted names or raw IP addresses.
    key = models.CharField(max_length=64, primary_key=True)
    started_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)


class InternalNonce(models.Model):
    # Only digest + expiry, never request bodies, sessions or credentials.
    digest = models.CharField(max_length=64, primary_key=True)
    expires_at = models.DateTimeField(db_index=True)
