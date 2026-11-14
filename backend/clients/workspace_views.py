from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.types import OpenApiTypes
from .models import Interaction, Opportunity
from .serializers import PartySerializer
from .workspace import (
    accessible,
    allowed,
    create_party,
    edit_identity,
    edit_profile,
    save_activity,
    IdentityInput,
    ProfileInput,
    InteractionInput,
    OpportunityInput,
)


class InteractionOutput(serializers.ModelSerializer):
    class Meta:
        model = Interaction
        fields = [
            "id",
            "kind",
            "subject",
            "notes",
            "occurred_at",
            "version",
            "updated_at",
        ]


class OpportunityOutput(serializers.ModelSerializer):
    class Meta:
        model = Opportunity
        fields = [
            "id",
            "title",
            "notes",
            "amount",
            "currency",
            "status",
            "due_date",
            "version",
            "updated_at",
        ]


class ProfileOutput(serializers.Serializer):
    version = serializers.IntegerField()
    notes = serializers.CharField(allow_blank=True)
    email = serializers.CharField(allow_blank=True)
    phone = serializers.CharField(allow_blank=True)
    profession = serializers.CharField(allow_blank=True)
    sector = serializers.CharField(allow_blank=True)


class ProvenanceOutput(serializers.Serializer):
    identity_source = serializers.CharField()
    crm_source = serializers.CharField()
    synchronization = serializers.ChoiceField(choices=["not_connected"])
    last_local_source_as_of = serializers.DateTimeField(allow_null=True)


class WorkspaceOutput(PartySerializer):
    is_prospect = serializers.BooleanField()
    version = serializers.IntegerField()
    origin = serializers.CharField()
    identity = serializers.DictField(child=serializers.CharField())
    crm = ProfileOutput()
    permissions = serializers.DictField(child=serializers.BooleanField())
    provenance = ProvenanceOutput()
    ownership = serializers.DictField(child=serializers.CharField())
    relationship_manager = serializers.CharField(allow_null=True)

    class Meta(PartySerializer.Meta):
        fields = PartySerializer.Meta.fields + [
            "is_prospect",
            "version",
            "origin",
            "identity",
            "crm",
            "permissions",
            "provenance",
            "ownership",
            "relationship_manager",
        ]


class WorkspaceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: WorkspaceOutput})
    def get(self, request, party_id):
        party = accessible(request.user, party_id)
        profile = getattr(party, "crm_profile", None)
        crm = (
            {
                key: getattr(profile, key)
                for key in [
                    "notes",
                    "email",
                    "phone",
                    "profession",
                    "sector",
                    "version",
                    "updated_at",
                ]
            }
            if profile
            else {
                "version": 1,
                "notes": "",
                "email": "",
                "phone": "",
                "profession": "",
                "sector": "",
            }
        )
        financial = allowed(request.user, party, "clients.view_financial")
        last = party.accounts.order_by("-source_as_of").first() if financial else None
        identity = (
            {
                "first_name": party.physicalperson.first_name,
                "last_name": party.physicalperson.last_name,
            }
            if party.kind == "physical"
            else {"legal_name": party.legalentity.legal_name}
        )
        return Response(
            {
                **PartySerializer(party).data,
                "is_prospect": hasattr(party, 'prospect'),
                "version": party.version,
                "origin": party.origin,
                "identity": identity,
                "crm": crm,
                "relationship_manager": (
                    party.assigned_to.user.username if party.assigned_to_id else None
                ),
                "provenance": {
                    "identity_source": party.origin,
                    "crm_source": "AICED",
                    "synchronization": "not_connected",
                    "last_local_source_as_of": last.source_as_of if last else None,
                },
                "permissions": {
                    "edit_identity": party.origin == "AICED"
                    and not party.externalidentity_set.exists()
                    and allowed(request.user, party, "clients.update_identity"),
                    "edit_crm": allowed(request.user, party, "clients.update_crm"),
                    "view_accounts": financial,
                    "view_interactions": allowed(
                        request.user, party, "interactions.view"
                    ),
                    "manage_interactions": allowed(
                        request.user, party, "interactions.manage"
                    ),
                    "view_opportunities": allowed(
                        request.user, party, "opportunities.view"
                    ),
                    "manage_opportunities": allowed(
                        request.user, party, "opportunities.manage"
                    ),
                },
                "ownership": {
                    "identity": party.origin,
                    "crm": "AICED",
                    "interactions": "AICED",
                    "opportunities": "AICED",
                    "accounts": "SOURCE_READ_ONLY",
                },
            }
        )


class CreatePartyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=IdentityInput, responses={201: PartySerializer})
    def post(self, request):
        return Response(
            PartySerializer(create_party(request.user, request.data, request)).data,
            status=201,
        )


class ClientContextView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        from iam_consumer.compat import Organization
        from identity.policies import organization_ids

        orgs = Organization.objects.filter(
            pk__in=organization_ids(request.user, "clients.create", True)
        ).filter(pk__in=organization_ids(request.user, "clients.view", True))
        return Response(
            {"organizations": [{"id": org.pk, "name": org.name} for org in orgs]}
        )


class IdentityEditView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=IdentityInput, responses={200: PartySerializer})
    def patch(self, request, party_id):
        return Response(
            PartySerializer(
                edit_identity(request.user, party_id, request.data, request)
            ).data
        )


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ProfileInput, responses={200: OpenApiTypes.OBJECT})
    def patch(self, request, party_id):
        profile = edit_profile(request.user, party_id, request.data, request)
        return Response({"version": profile.version})


class ActivityView(APIView):
    permission_classes = [IsAuthenticated]
    category = "interactions"
    http_method_names = ["get", "post", "options"]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, party_id, activity_id=None):
        party = accessible(
            request.user,
            party_id,
            (
                "interactions.view"
                if self.category == "interactions"
                else "opportunities.view"
            ),
        )
        model, output = (
            (Interaction, InteractionOutput)
            if self.category == "interactions"
            else (Opportunity, OpportunityOutput)
        )
        items = model.objects.filter(party=party)
        if activity_id:
            return Response(output(get_object_or_404(items, pk=activity_id)).data)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(items, request)
        return paginator.get_paginated_response(output(page, many=True).data)

    @extend_schema(request=InteractionInput, responses={201: InteractionOutput})
    def post(self, request, party_id):
        item = save_activity(
            request.user, party_id, self.category, request.data, request=request
        )
        return Response(
            (
                InteractionOutput
                if self.category == "interactions"
                else OpportunityOutput
            )(item).data,
            status=201,
        )

    @extend_schema(request=InteractionInput, responses={200: InteractionOutput})
    def patch(self, request, party_id, activity_id):
        item = save_activity(
            request.user, party_id, self.category, request.data, activity_id, request
        )
        return Response(
            (
                InteractionOutput
                if self.category == "interactions"
                else OpportunityOutput
            )(item).data
        )


class OpportunitiesView(ActivityView):
    category = "opportunities"

    @extend_schema(request=OpportunityInput, responses={201: OpportunityOutput})
    def post(self, *args, **kwargs):
        return super().post(*args, **kwargs)

    @extend_schema(request=OpportunityInput, responses={200: OpportunityOutput})
    def patch(self, *args, **kwargs):
        return super().patch(*args, **kwargs)


class InteractionDetailView(ActivityView):
    http_method_names = ["get", "patch", "options"]

    @extend_schema(
        operation_id="client_interaction_detail", responses={200: InteractionOutput}
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)


class OpportunityDetailView(OpportunitiesView):
    http_method_names = ["get", "patch", "options"]

    @extend_schema(
        operation_id="client_opportunity_detail", responses={200: OpportunityOutput}
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)
