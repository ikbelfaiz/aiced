import json
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from core.serializers import StrictSerializer
from internal_api.views import PrivateView, PrincipalInput, Credentials, resolve
from internal_api.client import ServiceUnavailable
from identity.policies import grants, organization_ids
from identity.models import Membership, Organization, User


def bounded(data):
    if len(json.dumps(data, default=str).encode()) > 60000:
        raise ServiceUnavailable("Contrat trop volumineux.")
    return Response(data)


class GrantSnapshotView(PrivateView):
    def post(self, request):
        if self.service not in ("client_crm", "commercial"):
            raise PermissionDenied()
        data = self.validated(PrincipalInput, request)
        actor = resolve(data["credentials"])
        # The current residue owns both Client and Commercial. This compatibility
        # contract supplies grants, never decides business-object access.
        prefixes = (
            ("clients.", "prospects.", "interactions.", "opportunities.", "audit.")
            if self.service == "client_crm"
            else ("opportunities.",)
        )
        rows = []
        orgs = {}
        for grant in (
            grants(actor)
            .select_related("membership__organization", "role")
            .prefetch_related("role__permissions")
        ):
            org = grant.membership.organization
            for cap in grant.role.permissions.all():
                if cap.code.startswith(prefixes):
                    rows.append(
                        {
                            "capability": cap.code,
                            "organization_id": str(org.pk),
                            "membership_id": str(grant.membership_id),
                            "scope": grant.scope,
                        }
                    )
                    orgs[str(org.pk)] = {"id": str(org.pk), "name": org.name}
        if len(rows) > 1000 or len(orgs) > 1000:
            raise ServiceUnavailable()
        return bounded(
            {
                "actor_id": str(actor.pk),
                "username": actor.username,
                "grants": rows,
                "organizations": list(orgs.values()),
            }
        )


class ReferenceInput(PrincipalInput):
    organization_id = serializers.UUIDField()
    membership_ids = serializers.ListField(
        child=serializers.UUIDField(), max_length=100
    )


class ReferenceView(PrivateView):
    def post(self, request):
        if self.service != "client_crm":
            raise PermissionDenied()
        data = self.validated(ReferenceInput, request)
        actor = resolve(data["credentials"])
        if (
            not organization_ids(actor, "clients.view", True)
            .filter(membership__organization_id=data["organization_id"])
            .exists()
        ):
            raise PermissionDenied()
        members = Membership.objects.filter(
            pk__in=data["membership_ids"],
            organization_id=data["organization_id"],
            is_active=True,
            user__is_active=True,
            organization__is_active=True,
        ).select_related("user")
        result = [
            {
                "id": str(m.pk),
                "organization_id": str(m.organization_id),
                "user_id": str(m.user_id),
                "username": m.user.username,
            }
            for m in members
        ]
        if len(result) != len(set(data["membership_ids"])):
            raise PermissionDenied("Reference invalide.")
        return bounded({"memberships": result})


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
    def post(self, request):
        if self.service != "client_crm":
            raise PermissionDenied()
        data = self.validated(QueryInput, request)
        actor = resolve(data["credentials"])
        from audit.models import AuditEvent

        allowed = organization_ids(actor, "audit.view", True)
        if not allowed.exists():
            raise PermissionDenied()
        qs = AuditEvent.objects.filter(organization_id__in=allowed)
        count = qs.count()
        if "before" in data:
            qs = qs.filter(
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
        from audit.views import AuditSerializer

        return bounded(
            {
                "count": count,
                "results": AuditSerializer(
                    qs.order_by("-occurred_at", "-id")[: data["limit"]], many=True
                ).data,
            }
        )


class ReadyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        from django.db import connection
        from iam_control.middleware import admit

        admit()
        with connection.cursor() as c:
            c.execute("SELECT 1")
        return Response({"ready": True})


class RevokeSessionView(PrivateView):
    def post(self, request):
        if self.service not in ("client_crm", "commercial", "integration"):
            raise PermissionDenied()
        data = self.validated(PrincipalInput, request)
        if data["credentials"]["method"] != "POST":
            raise PermissionDenied()
        actor = resolve(data["credentials"])
        from django.db import transaction
        from django.contrib.sessions.backends.db import SessionStore
        from identity.coordination import barrier, session_user
        from audit.services import record

        with transaction.atomic():
            barrier(exclusive=True)
            current = session_user(data["credentials"]["session_key"])
            if current.pk != actor.pk:
                raise PermissionDenied()
            SessionStore(session_key=data["credentials"]["session_key"]).delete()
            record("logout.succeeded", actor=current, request=request)
        return Response({"revoked": True, "actor_id": str(actor.pk)})
