from django.db import transaction
from django.http import JsonResponse
from django.db.models import Q
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from internal_api.base import PrivateView
from internal_api.contracts import PrincipalInput
from internal_api.client import ServiceUnavailable
from commercial_store.models import Journal
from .access import principal
from .gate import admit


class QueryInput(PrincipalInput):
    offset = serializers.IntegerField(min_value=0, max_value=0, default=0)
    limit = serializers.IntegerField(min_value=1, max_value=100)
    before = serializers.DateTimeField(required=False)
    before_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if ("before" in data) != ("before_id" in data):
            raise serializers.ValidationError("Curseur incomplet.")
        return data


class JournalView(PrivateView):
    audience = "commercial"

    @transaction.atomic
    def post(self, request):
        if self.service != "client_crm":
            raise PermissionDenied()
        admit()
        data = self.validated(QueryInput, request)
        _, decision = principal(data["credentials"])
        try:
            from uuid import UUID

            orgs = [
                UUID(r["organization_id"])
                for r in decision["grants"]
                if r["capability"] == "audit.view" and r["scope"] == "organization"
            ]
        except (KeyError, ValueError, TypeError):
            raise ServiceUnavailable()
        if not orgs:
            raise PermissionDenied()
        rows = Journal.objects.filter(organization_id__in=orgs)
        count = rows.count()
        if "before" in data:
            rows = rows.filter(
                Q(occurred_at__lt=data["before"])
                | Q(occurred_at=data["before"], id__lt=data["before_id"])
            )
        result = list(
            rows.values(
                "id",
                "occurred_at",
                "actor_id",
                "organization_id",
                "action",
                "target_id",
                "result",
                "request_id",
                "context",
            )[: data["limit"]]
        )
        import json
        from django.core.serializers.json import DjangoJSONEncoder

        if len(json.dumps(result, cls=DjangoJSONEncoder).encode()) > 60000:
            raise ServiceUnavailable()
        return Response({"count": count, "results": result})


@transaction.atomic
def ready(request):
    try:
        admit()
        return JsonResponse({"ready": True, "service": "commercial"})
    except ServiceUnavailable:
        return JsonResponse({"ready": False}, status=503)
