from django.http import JsonResponse
from django.db import connection
from django.urls import path
from django.conf import settings
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from core.serializers import StrictSerializer
from internal_api.security import authenticate
from .access import iam
from integration_store.models import Journal


class QueryInput(StrictSerializer):
    credentials = serializers.DictField()
    offset = serializers.IntegerField(min_value=0)
    limit = serializers.IntegerField(min_value=1, max_value=100)
    before = serializers.DateTimeField(required=False)
    before_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if ("before" in data) != ("before_id" in data) or (
            "before" in data and data["offset"]
        ):
            raise serializers.ValidationError(
                "Curseur incomplet ou offset incompatible."
            )
        return data


class AuditQuery(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        if authenticate(request, "integration") not in ("iam", "client_crm"):
            raise PermissionDenied("Service non autorisé.")
        super().initial(request, *args, **kwargs)

    def post(self, request):
        value = QueryInput(data=request.data)
        value.is_valid(raise_exception=True)
        data = value.validated_data
        decision = iam().post(
            "/internal/v1/imports/audit-scope", {"credentials": data["credentials"]}
        )
        # IAM owns the audit grants; Integration applies the organization filter
        # before counting/pagination. No finance requirement is invented here.
        from uuid import UUID

        try:
            organizations = [UUID(org) for org in decision["organizations"]]
            if not organizations:
                raise PermissionDenied("Audit non autorisé.")
        except (KeyError, TypeError, ValueError):
            from internal_api.client import ServiceUnavailable

            raise ServiceUnavailable()
        rows = Journal.objects.filter(
            organization_id__in=organizations, action__startswith="imports."
        )
        count = rows.count()
        if "before" in data:
            from django.db.models import Q

            rows = rows.filter(
                Q(occurred_at__lt=data["before"])
                | Q(occurred_at=data["before"], id__lt=data["before_id"])
            )
        fields = [
            "id",
            "occurred_at",
            "actor_id",
            "organization_id",
            "action",
            "target_id",
            "result",
            "request_id",
            "context",
        ]
        results = list(
            rows.values(*fields)[data["offset"] : data["offset"] + data["limit"]]
        )
        # Bound the signed response; small chunks preserve arbitrarily large journals.
        import json
        from django.core.serializers.json import DjangoJSONEncoder

        if len(json.dumps(results, cls=DjangoJSONEncoder).encode()) > 60000:
            from internal_api.client import ServiceUnavailable

            raise ServiceUnavailable("Page audit trop volumineuse.")
        return Response({"count": count, "results": results})


def live(request):
    return JsonResponse({"status": "ok", "service": "integration"})


def ready(request):
    from core.import_gate import mode

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        if mode() != "service":
            raise RuntimeError("Frozen")
        # Signed machine probe verifies IAM transport/registry/database access.
        decision = iam().post("/internal/v1/integration/ready", {})
        if (
            decision.get("ready") is not True
            or decision.get("database") != settings.DATABASES["default"]["NAME"]
        ):
            raise RuntimeError("IAM not ready")
        return JsonResponse({"status": "ready"})
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)


urlpatterns = [
    path("internal/v1/integration/audit/query", AuditQuery.as_view()),
    path("health/live", live),
    path("health/ready", ready),
]
from .source_mapping import MappingPreview
urlpatterns += [path('internal/v1/source-mapping/preview', MappingPreview.as_view())]
