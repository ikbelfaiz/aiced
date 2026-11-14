"""Immediate three-journal audit; fail closed, scoped before count, bounded chunks."""

import time
from uuid import UUID
from django.conf import settings
from django.db.models import Q
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param, remove_query_param
from internal_api.client import InternalClient, ServiceUnavailable, request_credentials
from identity.policies import organization_ids
from .federation import sortkey

IAM_ACTION = (
    Q(action__startswith="users.")
    | Q(action__startswith="permissions.")
    | Q(action__startswith="membership.")
    | Q(action__startswith="login.")
    | Q(action__startswith="logout.")
)


def page(request, local):
    allowed = {str(v) for v in organization_ids(request.user, "audit.view", True)}
    if not allowed:
        raise ServiceUnavailable()
    raw = request.query_params.get("page", "1")
    try:
        number = int(raw) if raw != "last" else 1
        if number < 1:
            raise ValueError()
    except ValueError:
        raise NotFound("Page invalide.")
    credentials = request_credentials(request)
    deadline = time.monotonic() + 12

    def stream(url, key_id, audience, path, imports=False):
        peer = InternalClient(
            url, key_id, settings.AICED_INTERNAL_KEYS[key_id]["secret"], audience
        )

        def fetch(before=None):
            if time.monotonic() > deadline:
                raise ServiceUnavailable()
            body = {"credentials": credentials, "offset": 0, "limit": 100}
            if before:
                body.update(before=before["occurred_at"], before_id=before["id"])
            data = peer.post(path, body)
            try:
                if (
                    type(data["count"]) is not int
                    or data["count"] < 0
                    or not isinstance(data["results"], list)
                    or len(data["results"]) > 100
                ):
                    raise ValueError()
                previous = sortkey(before) if before else None
                for row in data["results"]:
                    for field in ["id", "organization_id", "request_id"]:
                        UUID(row[field])
                    if row["actor_id"]:
                        UUID(row["actor_id"])
                    if (
                        row["organization_id"] not in allowed
                        or not isinstance(row["context"], dict)
                        or (imports and not row["action"].startswith("imports."))
                    ):
                        raise ValueError()
                    key = sortkey(row)
                    if previous is not None and key >= previous:
                        raise ValueError()
                    previous = key
            except (KeyError, ValueError, TypeError, AttributeError):
                raise ServiceUnavailable()
            return data

        first = fetch()

        def iterator():
            data = first
            seen = 0
            while True:
                for row in data["results"]:
                    yield row
                seen += len(data["results"])
                if seen >= first["count"]:
                    return
                if not data["results"]:
                    raise ServiceUnavailable()
                data = fetch(data["results"][-1])

        return first["count"], iterator()

    from iam_consumer.models import IAMJournalRef

    local = local.exclude(pk__in=IAMJournalRef.objects.values("event_id"))
    if getattr(settings, "COMMERCIAL_REMOTE", False):
        from iam_consumer.models import CommercialJournalRef
        local = local.exclude(pk__in=CommercialJournalRef.objects.values("event_id")).exclude(action__startswith="clients.opportunities")
    sources = [
        (
            local.exclude(IAM_ACTION).exclude(action__startswith="imports.").count(),
            iter(
                local.exclude(IAM_ACTION)
                .exclude(action__startswith="imports.")
                .values(
                    "id",
                    "occurred_at",
                    "actor_id",
                    "organization_id",
                    "action",
                    "target_id",
                    "result",
                    "request_id",
                    "context",
                )
                .iterator(chunk_size=100)
            ),
        )
    ]
    sources.append(
        stream(
            settings.IAM_URL,
            settings.IAM_CONSUMER_KEY_ID,
            "iam",
            "/internal/v1/iam/audit/query",
        )
    )
    sources.append(
        stream(
            settings.INTEGRATION_AUDIT_URL,
            settings.INTEGRATION_AUDIT_KEY_ID,
            "integration",
            "/internal/v1/integration/audit/query",
            True,
        )
    )
    if getattr(settings, "COMMERCIAL_REMOTE", False):
        sources.append(stream(settings.COMMERCIAL_AUDIT_URL, settings.COMMERCIAL_AUDIT_KEY_ID, "commercial", "/internal/v1/commercial/audit/query"))
    total = sum(count for count, _ in sources)
    size = settings.REST_FRAMEWORK.get("PAGE_SIZE", 50)
    if raw == "last":
        number = max(1, (total + size - 1) // size)
    if number > max(1, (total + size - 1) // size):
        raise NotFound("Page invalide.")
    heads = [next(it, None) for _, it in sources]
    output = []
    start = (number - 1) * size
    end = min(number * size, total)
    for i in range(end):
        valid = [j for j, row in enumerate(heads) if row is not None]
        if not valid:
            raise ServiceUnavailable()
        j = max(valid, key=lambda k: sortkey(heads[k]))
        row = heads[j]
        if i >= start:
            output.append(row)
        heads[j] = next(sources[j][1], None)
    url = request.build_absolute_uri()
    from .views import AuditSerializer

    return Response(
        {
            "count": total,
            "next": (
                replace_query_param(url, "page", number + 1) if end < total else None
            ),
            "previous": (
                (
                    remove_query_param(url, "page")
                    if number == 2
                    else replace_query_param(url, "page", number - 1)
                )
                if number > 1
                else None
            ),
            "results": AuditSerializer(output, many=True).data,
        }
    )
