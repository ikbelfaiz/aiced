from identity.coordination import admit
"""Client workspace: explicit field allowlists and serialized, object-scoped writes."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, APIException
from django.utils import timezone
from core.serializers import StrictSerializer
from commercial.contracts import OpportunityInput
from iam_consumer.compat import Organization
from identity.policies import require
from .policies import client_queryset
from audit.services import record
from .models import (
    Party,
    PhysicalPerson,
    LegalEntity,
    CRMProfile,
    Interaction,
)


class Conflict(APIException):
    status_code = 409
    default_detail = "Version obsolète. Rechargez les données avant de modifier."


def accessible(actor, party_id, capability="clients.view", lock=False, request=None):
    visible = client_queryset(actor, "clients.view")
    qs = client_queryset(actor, capability).filter(pk__in=visible.values("pk"))
    candidate = get_object_or_404(qs, pk=party_id)
    if lock:
        Organization.objects.select_for_update().get(pk=candidate.organization_id)
        admit(actor, request)
        qs = client_queryset(actor, capability).filter(
            pk__in=client_queryset(actor, "clients.view").values("pk")
        )
        return get_object_or_404(qs.select_for_update(of=("self",)), pk=party_id)
    return candidate


def allowed(actor, party, capability):
    return client_queryset(actor, capability).filter(pk=party.pk).exists()


class IdentityInput(StrictSerializer):
    version = serializers.IntegerField(min_value=1, required=False)
    organization_id = serializers.UUIDField(required=False)
    kind = serializers.ChoiceField(choices=Party.Kind.choices, required=False)
    first_name = serializers.CharField(max_length=100, required=False)
    last_name = serializers.CharField(max_length=100, required=False)
    legal_name = serializers.CharField(max_length=200, required=False)


class ProfileInput(StrictSerializer):
    version = serializers.IntegerField(min_value=1)
    notes = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    email = serializers.EmailField(allow_blank=True, required=False)
    phone = serializers.RegexField(
        r"^[0-9+(). /-]{0,40}$", allow_blank=True, required=False
    )
    profession = serializers.CharField(max_length=120, allow_blank=True, required=False)
    sector = serializers.CharField(max_length=120, allow_blank=True, required=False)


class InteractionInput(StrictSerializer):
    version = serializers.IntegerField(min_value=1, required=False)
    kind = serializers.ChoiceField(choices=["call", "email", "meeting", "visit"])
    subject = serializers.CharField(max_length=160)
    notes = serializers.CharField(max_length=5000, allow_blank=True, default="")
    occurred_at = serializers.DateTimeField()

    def validate_occurred_at(self, value):
        if value > timezone.now():
            raise serializers.ValidationError(
                "Une interaction réalisée ne peut être datée dans le futur."
            )
        return value




def validate(schema, data, partial=False):
    serializer = schema(data=data, partial=partial)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


def check_version(instance, data):
    if data.pop("version", None) != instance.version:
        raise Conflict()


def set_identity(party, data):
    if party.kind == "physical":
        if set(data) != {"first_name", "last_name"}:
            raise serializers.ValidationError(
                "Prénom et nom requis, aucun autre champ autorisé."
            )
        person, _ = PhysicalPerson.objects.get_or_create(party=party, defaults=data)
        person.first_name, person.last_name = data["first_name"], data["last_name"]
        person.save()
        party.display_name = f"{person.first_name} {person.last_name}"
    else:
        if set(data) != {"legal_name"}:
            raise serializers.ValidationError(
                "Raison sociale requise, aucun autre champ autorisé."
            )
        person, _ = LegalEntity.objects.get_or_create(party=party, defaults=data)
        person.legal_name = data["legal_name"]
        person.save()
        party.display_name = person.legal_name
    if len(party.display_name) > 200:
        raise serializers.ValidationError(
            "Le nom complet ne peut dépasser 200 caractères."
        )
    party.save()


@transaction.atomic
def create_party(actor, data, request=None):
    values = validate(IdentityInput, data)
    org_id, kind = values.pop("organization_id", None), values.pop("kind", None)
    if org_id is None or kind is None or "version" in values:
        raise serializers.ValidationError(
            "Organisation et type requis ; version interdite à la création."
        )
    require(actor, "clients.create", org_id, full_scope=True)
    Organization.objects.select_for_update().get(pk=org_id)
    admit(actor, request)
    require(actor, "clients.create", org_id, full_scope=True)
    require(actor, "clients.view", org_id, full_scope=True)
    party = Party.objects.create(organization_id=org_id, kind=kind, origin="AICED")
    set_identity(party, values)
    CRMProfile.objects.create(party=party, updated_by=actor)
    record(
        "clients.created",
        actor=actor,
        organization_id=org_id,
        target_id=party.pk,
        request=request,
    )
    return party


@transaction.atomic
def edit_identity(actor, party_id, data, request=None):
    party = accessible(actor, party_id, "clients.update_identity", lock=True, request=request)
    if party.origin != "AICED" or party.externalidentity_set.exists():
        raise PermissionDenied("Identité source en lecture seule.")
    values = validate(IdentityInput, data)
    check_version(party, values)
    party.version += 1
    set_identity(party, values)
    record(
        "clients.identity_updated",
        actor=actor,
        organization_id=party.organization_id,
        target_id=party.pk,
        request=request,
    )
    return party


@transaction.atomic
def edit_profile(actor, party_id, data, request=None):
    party = accessible(actor, party_id, "clients.update_crm", lock=True, request=request)
    values = validate(ProfileInput, data)
    profile, _ = CRMProfile.objects.get_or_create(party=party)
    check_version(profile, values)
    for key, value in values.items():
        setattr(profile, key, value)
    profile.version += 1
    profile.updated_by = actor
    profile.save()
    record(
        "clients.profile_updated",
        actor=actor,
        organization_id=party.organization_id,
        target_id=party.pk,
        request=request,
    )
    return profile


@transaction.atomic
def save_activity(actor, party_id, category, data, activity_id=None, request=None):
    if category == "opportunities":
        from commercial.services import save_opportunity

        return save_opportunity(actor, party_id, data, activity_id, request)
    if category != "interactions":
        raise serializers.ValidationError("Type d\u2019activit\u00e9 inconnu.")
    party = accessible(actor, party_id, "interactions.manage", lock=True, request=request)
    accessible(actor, party_id, "interactions.view")
    model, schema = Interaction, InteractionInput
    values = validate(schema, data, partial=activity_id is not None)
    if activity_id:
        item = get_object_or_404(
            model.objects.select_for_update(), pk=activity_id, party=party
        )
        check_version(item, values)
        for key, value in values.items():
            setattr(item, key, value)
        item.version += 1
        item.save()
    else:
        if "version" in values:
            raise serializers.ValidationError("Version interdite à la création.")
        item = model.objects.create(party=party, author=actor, **values)
    record(
        f"clients.{category}_saved",
        actor=actor,
        organization_id=party.organization_id,
        target_id=item.pk,
        request=request,
    )
    return item
