"""Fresh delegated IAM decisions. No identity ORM or caller-supplied roles."""

from uuid import UUID
import re
from django.conf import settings
from django.db import transaction
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import PermissionDenied
from core.admission import barrier
from internal_api.client import InternalClient, ServiceUnavailable, request_credentials
from integration_store.models import ActorRef, OrganizationRef, Journal


def iam(audience="iam"):
    key = settings.AICED_INTERNAL_KEYS[settings.INTEGRATION_KEY_ID]
    return InternalClient(
        settings.IAM_URL, settings.INTEGRATION_KEY_ID, key["secret"], audience
    )


class DelegatedSession(BaseAuthentication):
    def authenticate(self, request):
        session = request.COOKIES.get(settings.SESSION_COOKIE_NAME, "")
        if not re.fullmatch(r"[a-z0-9]{32}", session):
            return None
        credentials = request_credentials(request)
        result = iam().post(
            "/internal/v1/principal/resolve", {"credentials": credentials}
        )
        try:
            actor = ActorRef(id=UUID(result["actor_id"]))
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ServiceUnavailable() from exc
        actor.credentials = credentials  # Request-scoped; never persisted/logged.
        return actor, None


class RemoteAccess:
    def authorize(
        self,
        actor,
        organization_id,
        capability="imports.view",
        lock=False,
        request=None,
    ):
        if not actor or not getattr(actor, "credentials", None):
            # Jobs must provide a real delegated principal; UUID alone never grants access.
            raise PermissionDenied("Délégation IAM requise.")
        if lock:
            from core.import_gate import admit

            admit(lock=True)
            if not transaction.get_connection().in_atomic_block:
                raise RuntimeError("Mutation requires local transaction")
            # Serialize quota/idempotency per org without reading IAM tables.
            # Advisory hash collisions can only cause extra contention.
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    [UUID(str(organization_id)).int % (2**63 - 1)],
                )
            barrier()
        result = iam().authorize(
            {
                "credentials": actor.credentials,
                "organization_id": str(organization_id),
                "capabilities": list(
                    dict.fromkeys(
                        ["imports.view", "clients.view_financial", capability]
                    )
                ),
            }
        )
        if result["actor_id"] != str(actor.pk) or any(
            row["scope"] != "organization" for row in result["grants"]
        ):
            raise PermissionDenied("Périmètre d’import non autorisé.")
        if lock:
            # Only fresh successful IAM validation can mint persistent references.
            OrganizationRef.objects.get_or_create(pk=organization_id)
            ActorRef.objects.get_or_create(pk=actor.pk)

    def context(self, actor):
        result = iam().post(
            "/internal/v1/imports/context", {"credentials": actor.credentials}
        )
        rows = result.get("organizations")
        if not isinstance(rows, list):
            raise ServiceUnavailable()
        try:
            for row in rows:
                UUID(row["id"])
                if not isinstance(row["name"], str) or any(
                    type(row[key]) is not bool
                    for key in ("upload", "approve", "policy_manage", "create_client")
                ):
                    raise ValueError("Invalid context")
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ServiceUnavailable() from exc
        return rows

    def history(self, organization_id, batch_id):
        return Journal.objects.filter(
            organization_id=organization_id, target_id=batch_id
        ).order_by("occurred_at")[:100]

    def record(self, *args, **kwargs):
        from .journal import record

        return record(*args, **kwargs)
