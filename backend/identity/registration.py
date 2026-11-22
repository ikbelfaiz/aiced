"""Self-service requests; activation never grants business permissions."""
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, PermissionDenied

from audit.services import record
from core.serializers import StrictSerializer
from .coordination import admit
from .models import User, Organization, Membership, RegistrationRequest
from .policies import require


class RegistrationSerializer(StrictSerializer):
    username = serializers.CharField(max_length=150, validators=[UnicodeUsernameValidator()])
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=4096, trim_whitespace=False, write_only=True)
    organization_code = serializers.CharField(max_length=60)


class RegistrationDecisionSerializer(StrictSerializer):
    decision = serializers.ChoiceField(choices=['approved', 'rejected'])


class RegistrationItemSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = RegistrationRequest
        fields = ['id', 'username', 'email', 'status', 'created_at', 'reviewed_at']


@transaction.atomic
def request_registration(data, request=None):
    serializer = RegistrationSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    user = User(username=values['username'], email=values['email'], is_active=False)
    try:
        validate_password(values['password'], user)
    except DjangoValidationError as exc:
        raise ValidationError({'password': exc.messages})
    # Hash on every valid request, including duplicates, without logging credentials.
    user.set_password(values['password'])
    org = Organization.objects.select_for_update().filter(code=values['organization_code'], is_active=True).first()
    if org is None or User.objects.filter(username=user.username).exists():
        return
    try:
        with transaction.atomic():
            user.save()
    except IntegrityError:
        return  # Concurrent username reservation: same public response.
    item = RegistrationRequest.objects.create(user=user, organization=org)
    record('registration.requested', organization_id=org.pk, target_id=item.pk, request=request)


@transaction.atomic
def review_registration(actor, organization_id, registration_id, data, request=None):
    require(actor, 'users.manage', organization_id, full_scope=True)
    serializer = RegistrationDecisionSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    Organization.objects.select_for_update().get(pk=organization_id)
    admit(actor, request, exclusive=True)
    require(actor, 'users.manage', organization_id, full_scope=True)
    item = get_object_or_404(RegistrationRequest.objects.select_for_update(), pk=registration_id, organization_id=organization_id)
    if item.user_id == actor.pk:
        raise PermissionDenied('Vous ne pouvez pas approuver votre propre demande.')
    if item.status != RegistrationRequest.Status.PENDING:
        raise ValidationError('Cette demande a déjà été traitée.')
    user = User.objects.select_for_update().get(pk=item.user_id)
    if user.is_active or Membership.objects.filter(user=user).exists():
        raise ValidationError('Le compte a changé. Une vérification administrative est nécessaire.')
    item.status = serializer.validated_data['decision']
    if item.status == RegistrationRequest.Status.APPROVED:
        user.is_active = True
        user.save(update_fields=['is_active'])
        Membership.objects.create(user=user, organization_id=organization_id)
    item.reviewed_by = actor
    item.reviewed_at = timezone.now()
    item.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
    record(f'registration.{item.status}', actor=actor, organization_id=organization_id, target_id=item.pk, request=request)
    return item
