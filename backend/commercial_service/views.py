from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from core.client_admission import scope_fence
from commercial.contracts import OpportunityInput
from commercial_store.models import Opportunity, PartyRef, ActorRef
from .access import principal, authorize
from .gate import admit
from .journal import record


class Conflict(APIException):
    status_code = 409
    default_detail = (
        "Version obsol\u00e8te. Rechargez les donn\u00e9es avant de modifier."
    )


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


class OpportunitiesView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "options"]

    @transaction.atomic
    def get(self, request, party_id, activity_id=None):
        admit()
        authorize(request.user, party_id, "opportunities.view")
        items = Opportunity.objects.filter(party_id=party_id)
        if activity_id:
            return Response(
                OpportunityOutput(get_object_or_404(items, pk=activity_id)).data
            )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(items, request)
        return paginator.get_paginated_response(OpportunityOutput(page, many=True).data)

    def post(self, request, party_id):
        return self.save(request, party_id)

    def patch(self, request, party_id, activity_id):
        return self.save(request, party_id, activity_id)

    @transaction.atomic
    def save(self, request, party_id, activity_id=None):
        admit()
        scope_fence()  # held through required local journal/outbox and commit
        actor, _ = principal(request.user.credentials)
        if actor.pk != request.user.pk:
            raise ValidationError("Identite incoherente.")
        decision = authorize(actor, party_id, "opportunities.manage")
        schema = OpportunityInput(data=request.data, partial=activity_id is not None)
        schema.is_valid(raise_exception=True)
        values = dict(schema.validated_data)
        reference, _ = PartyRef.objects.get_or_create(
            pk=party_id, defaults={"organization_id": decision["organization_id"]}
        )
        if str(reference.organization_id) != decision["organization_id"]:
            raise Conflict("Reference Client incoherente.")
        author, _ = ActorRef.objects.get_or_create(
            pk=actor.pk, defaults={"username": actor.username}
        )
        if activity_id:
            item = get_object_or_404(
                Opportunity.objects.select_for_update(),
                pk=activity_id,
                party_id=party_id,
            )
            if values.pop("version", None) != item.version:
                raise Conflict()
            for key, value in values.items():
                setattr(item, key, value)
            item.version += 1
            item.save()
        else:
            if "version" in values:
                raise ValidationError("Version interdite \u00e0 la cr\u00e9ation.")
            item = Opportunity.objects.create(party=reference, author=author, **values)
        if (
            record(
                "clients.opportunities_saved",
                actor=actor,
                organization_id=reference.organization_id,
                target_id=item.pk,
                request=request,
            )
            is None
        ):
            raise RuntimeError("Required local audit missing")
        return Response(
            OpportunityOutput(item).data, status=200 if activity_id else 201
        )


class OpportunityDetailView(OpportunitiesView):
    http_method_names = ["get", "patch", "options"]
