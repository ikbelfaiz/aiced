from identity.coordination import admit
"""AICED prospect services and scoped HTTP views; no source writes or conversion."""

from django.db import transaction
from django.db.models import Q, OuterRef, Subquery
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from core.serializers import StrictSerializer
from identity.models import Organization
from identity.policies import organization_ids, require, grants
from .policies import client_queryset
from audit.services import record
from .models import Prospect, Interaction
from .pagination import ClientPagination
from .workspace import IdentityInput, create_party, accessible, validate, check_version


class QualificationInput(StrictSerializer):
    version = serializers.IntegerField(min_value=1, required=False)
    source = serializers.CharField(max_length=120, allow_blank=True, required=False)
    status = serializers.ChoiceField(choices=Prospect.Status.choices, required=False)
    next_action = serializers.CharField(
        max_length=160, allow_blank=True, required=False
    )
    next_action_date = serializers.DateField(allow_null=True, required=False)


class ProspectCreateInput(IdentityInput):
    qualification = QualificationInput(required=False)


def validate_action(prospect):
    if prospect.next_action_date and not prospect.next_action:
        raise serializers.ValidationError(
            {"next_action": "Une action est requise avec sa date."}
        )


@transaction.atomic
def create_prospect(actor, data, request=None):
    values = validate(ProspectCreateInput, data)
    qualification = values.pop("qualification", {})
    if "version" in qualification:
        raise serializers.ValidationError("Version interdite à la création.")
    org_id = values.get("organization_id")
    require(actor, "prospects.manage", org_id, full_scope=True)
    Organization.objects.select_for_update().get(pk=org_id)
    admit(actor, request)
    require(actor, "prospects.manage", org_id, full_scope=True)
    require(actor, "prospects.view", org_id, full_scope=True)
    # Reuse the identity allowlist, transaction and mandatory client capabilities.
    party = create_party(actor, values, request)
    prospect = Prospect(party=party, **qualification)
    validate_action(prospect)
    prospect.save()
    record(
        "prospects.created",
        actor=actor,
        organization_id=org_id,
        target_id=party.pk,
        request=request,
    )
    return prospect


@transaction.atomic
def edit_prospect(actor, party_id, data, request=None):
    party = accessible(actor, party_id, "prospects.manage", lock=True, request=request)
    prospect = get_object_or_404(Prospect.objects.select_for_update(), party=party)
    values = validate(QualificationInput, data)
    check_version(prospect, values)
    for key, value in values.items():
        setattr(prospect, key, value)
    validate_action(prospect)
    prospect.version += 1
    prospect.save()
    record(
        "prospects.updated",
        actor=actor,
        organization_id=party.organization_id,
        target_id=party.pk,
        request=request,
    )
    return prospect


class ProspectOutput(serializers.ModelSerializer):
    id = serializers.UUIDField(source="party_id")
    display_name = serializers.CharField(source="party.display_name")
    kind = serializers.CharField(source="party.kind")
    created_at = serializers.DateTimeField(source="party.created_at")
    relationship_manager = serializers.CharField(
        source="party.assigned_to.user.username", default=None, allow_null=True
    )
    last_interaction = serializers.DateTimeField(read_only=True, allow_null=True)
    can_edit = serializers.SerializerMethodField()

    def get_can_edit(self, obj) -> bool:
        return (
            client_queryset(self.context["request"].user, "prospects.manage")
            .filter(pk=obj.party_id)
            .exists()
        )

    class Meta:
        model = Prospect
        fields = [
            "id",
            "display_name",
            "kind",
            "source",
            "status",
            "next_action",
            "next_action_date",
            "version",
            "created_at",
            "relationship_manager",
            "last_interaction",
            "can_edit",
        ]


class ProspectPageOutput(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = ProspectOutput(many=True)


def prospect_queryset(actor):
    visible = client_queryset(actor, "clients.view")
    scoped = client_queryset(actor, "prospects.view").filter(
        pk__in=visible.values("pk")
    )
    # Do not leak interaction dates when that capability is absent on this object.
    activities = Interaction.objects.filter(
        party_id=OuterRef("party_id"),
        party_id__in=client_queryset(actor, "interactions.view").values("pk"),
    ).order_by("-occurred_at", "id")
    return (
        Prospect.objects.filter(party_id__in=scoped.values("pk"))
        .select_related("party__assigned_to__user")
        .annotate(last_interaction=Subquery(activities.values("occurred_at")[:1]))
        .order_by("-party__created_at", "party_id")
    )


class ProspectsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="prospects_list", responses={200: ProspectPageOutput})
    def get(self, request):
        if not grants(request.user, "prospects.view").exists():
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied()
        queryset = prospect_queryset(request.user)
        search = request.query_params.get("search", "")
        if len(search) > 200:
            raise serializers.ValidationError({"search": "200 caractères maximum."})
        queryset = queryset.filter(
            Q(party__display_name__icontains=search) | Q(source__icontains=search)
        )
        status = request.query_params.get("status", "")
        if status:
            if status not in Prospect.Status.values:
                raise serializers.ValidationError({"status": "Statut inconnu."})
            queryset = queryset.filter(status=status)
        paginator = ClientPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(
            ProspectOutput(page, many=True, context={"request": request}).data
        )

    @extend_schema(request=ProspectCreateInput, responses={201: ProspectOutput})
    def post(self, request):
        prospect = create_prospect(request.user, request.data, request)
        return Response(
            ProspectOutput(prospect, context={"request": request}).data, status=201
        )


class ProspectView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: ProspectOutput})
    def get(self, request, party_id):
        return Response(
            ProspectOutput(
                get_object_or_404(prospect_queryset(request.user), pk=party_id),
                context={"request": request},
            ).data
        )

    @extend_schema(request=QualificationInput, responses={200: ProspectOutput})
    def patch(self, request, party_id):
        prospect = edit_prospect(request.user, party_id, request.data, request)
        return Response(ProspectOutput(prospect, context={"request": request}).data)


class ProspectContextView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        orgs = Organization.objects.all()
        for code in [
            "prospects.view",
            "prospects.manage",
            "clients.view",
            "clients.create",
        ]:
            orgs = orgs.filter(
                pk__in=organization_ids(request.user, code, full_scope=True)
            )
        return Response({"organizations": list(orgs.values("id", "name"))})
