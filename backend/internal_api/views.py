from django.conf import settings
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.test.client import RequestFactory
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from core.serializers import StrictSerializer
from identity.policies import grants
from .security import authenticate
from .contracts import Credentials, PrincipalInput
from .base import PrivateView




class CheckInput(StrictSerializer):
    credentials = Credentials()
    organization_id = serializers.UUIDField()
    capabilities = serializers.ListField(
        child=serializers.CharField(max_length=100), min_length=1, max_length=10
    )




class ClientInput(StrictSerializer):
    credentials = Credentials()
    party_id = serializers.UUIDField()
    capability = serializers.ChoiceField(
        choices=["opportunities.view", "opportunities.manage"]
    )


def resolve(data):
    if getattr(settings, 'IAM_REMOTE', False):
        from iam_consumer.access import read_principal
        return read_principal(data, persist=False)
    from identity.coordination import session_user
    actor = session_user(data["session_key"])
    if data["method"] not in ("GET", "HEAD", "OPTIONS"):
        # Preserve Django's cookie/token/origin rules for the original browser
        # mutation. Service authentication does not substitute for user CSRF.
        request = RequestFactory().generic(
            data["method"],
            "/delegated/",
            HTTP_HOST=data["host"],
            HTTP_X_CSRFTOKEN=data.get("csrf_token", ""),
            **{"wsgi.url_scheme": data["scheme"]}
        )
        if data.get("origin"):
            request.META["HTTP_ORIGIN"] = data["origin"]
        if data.get("referer"):
            request.META["HTTP_REFERER"] = data["referer"]
        request.COOKIES[settings.CSRF_COOKIE_NAME] = data.get("csrf_cookie", "")
        middleware = CsrfViewMiddleware(lambda req: HttpResponse())
        middleware.process_request(request)
        if (
            middleware.process_view(request, lambda req: HttpResponse(), (), {})
            is not None
        ):
            raise PermissionDenied("Vérification CSRF déléguée échouée.")
    return actor


def permitted(service, capability):
    prefixes = {
        "iam": ("users.", "audit."),
        "client_crm": ("clients.", "prospects.", "interactions."),
        "commercial": ("opportunities.",),
        "integration": ("imports.",),
    }
    return capability.startswith(prefixes[service]) or (
        service == "integration" and capability == "clients.view_financial"
    )




class PrincipalView(PrivateView):
    def post(self, request):
        data = self.validated(PrincipalInput, request)
        actor = resolve(data["credentials"])
        return Response({"actor_id": str(actor.pk)})


class AuthorizationView(PrivateView):
    def post(self, request):
        data = self.validated(CheckInput, request)
        if not all(permitted(self.service, code) for code in data["capabilities"]):
            raise PermissionDenied("Capacité hors audience du service.")
        actor = resolve(data["credentials"])
        rows = []
        for code in data["capabilities"]:
            current = grants(actor, code).filter(
                membership__organization_id=data["organization_id"]
            )
            if self.service == "integration":
                current = current.filter(scope="organization")
            if not current.exists():
                raise PermissionDenied("Autorisation révoquée ou insuffisante.")
            rows.extend(
                {
                    "capability": code,
                    "scope": grant.scope,
                    "membership_id": str(grant.membership_id),
                }
                for grant in current
            )
        return Response(
            {
                "authorized": True,
                "actor_id": str(actor.pk),
                "organization_id": str(data["organization_id"]),
                "grants": rows,
            }
        )


class ImportContextView(PrivateView):
    """Bounded delegation: organization references and UI flags, not client grants."""

    def post(self, request):
        if self.service != "integration":
            raise PermissionDenied("Service non autorisé.")
        data = self.validated(PrincipalInput, request)
        actor = resolve(data["credentials"])
        from ingestion.runtime import LegacyAccess

        rows = LegacyAccess().context(actor)
        # The internal contract is intentionally bounded. Never silently omit orgs.
        import json

        result = {"organizations": [{**row, "id": str(row["id"])} for row in rows]}
        if len(json.dumps(result).encode()) > 60000:
            from internal_api.client import ServiceUnavailable

            raise ServiceUnavailable(
                "Contexte trop volumineux ; contrat paginé requis."
            )
        return Response(result)


class ImportAuditScopeView(PrivateView):
    def post(self, request):
        if self.service != "integration":
            raise PermissionDenied("Service non autorisé.")
        data = self.validated(PrincipalInput, request)
        actor = resolve(data["credentials"])
        from identity.policies import organization_ids

        organizations = list(
            organization_ids(actor, "audit.view", full_scope=True).distinct()
        )
        if not organizations:
            raise PermissionDenied("Audit non autorisé.")
        return Response({"organizations": [str(org) for org in organizations]})


class IntegrationReadyView(PrivateView):
    def post(self, request):
        if self.service != "integration" or request.data:
            raise PermissionDenied("Appel non autorisé.")
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"ready": True, "database": connection.settings_dict["NAME"]})


from drf_spectacular.utils import extend_schema


@extend_schema(exclude=True)
class ClientAuthorizationView(PrivateView):
    audience = "client"

    def post(self, request):
        if self.service != "commercial":
            raise PermissionDenied("Service non autorisé.")
        data = self.validated(ClientInput, request)
        actor = resolve(data["credentials"])
        # IAM never owns this object-scoping decision.
        from clients.workspace import accessible

        party = accessible(actor, data["party_id"], data["capability"])
        accessible(actor, data["party_id"], "opportunities.view")
        return Response(
            {
                "authorized": True,
                "actor_id": str(actor.pk),
                "party_id": str(party.pk),
                "organization_id": str(party.organization_id),
                "version": party.version,
            }
        )


class AuditInput(StrictSerializer):
    event_id = serializers.UUIDField()
    occurred_at = serializers.DateTimeField()
    actor_id = serializers.UUIDField(allow_null=True)
    organization_id = serializers.UUIDField(allow_null=True)
    target_id = serializers.UUIDField(allow_null=True)
    request_id = serializers.UUIDField()
    action = serializers.RegexField(r"^[a-z][a-z0-9_.]{0,99}$")
    result = serializers.ChoiceField(choices=["success", "denied"])


class AuditView(PrivateView):
    audience = "audit"

    def post(self, request):
        data = self.validated(AuditInput, request)
        action = data["action"]
        common = action in ("access.denied", "csrf.denied")
        allowed = {
            "iam": action.startswith(
                ("users.", "membership.", "permissions.", "login.", "logout.")
            ),
            "integration": action.startswith("imports."),
            "commercial": action == "clients.opportunities_saved",
            "client_crm": action.startswith(("clients.", "prospects."))
            and not action.startswith("clients.opportunities"),
        }
        if not common and not allowed[self.service]:
            raise PermissionDenied("Événement hors domaine producteur.")
        # Service is taken from the authenticated key, never a body/header claim.
        from audit.delivery import receive

        # Serializer normalizes UUID/date without trusting extra fields.
        payload = dict(AuditInput(data).data)
        return Response(receive(self.service, payload))
