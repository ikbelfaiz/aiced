"""Merge scoped local/Integration journals without foreign SQL or stale fallback."""

import time
from datetime import datetime
from uuid import UUID
from django.conf import settings
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param, remove_query_param
from internal_api.client import InternalClient, ServiceUnavailable, request_credentials


def page(request, local):
    from identity.policies import organization_ids

    allowed = {
        str(org)
        for org in organization_ids(request.user, "audit.view", full_scope=True)
    }
    try:
        raw = request.query_params.get("page", "1")
        number = int(raw) if raw != "last" else 1
        if number < 1:
            raise ValueError()
    except (ValueError, TypeError):
        raise NotFound("Page invalide.")
    key_id = settings.INTEGRATION_AUDIT_KEY_ID
    key = settings.AICED_INTERNAL_KEYS[key_id]
    client = InternalClient(
        settings.INTEGRATION_AUDIT_URL, key_id, key["secret"], "integration"
    )
    credentials = request_credentials(request)
    deadline = time.monotonic() + 12

    def fetch(before=None):
        if time.monotonic() > deadline:
            raise ServiceUnavailable(
                "Lecture audit trop longue ; aucune réponse partielle."
            )
        payload = {"credentials": credentials, "offset": 0, "limit": 100}
        if before is not None:
            payload.update(before=before["occurred_at"], before_id=before["id"])
        data = client.post(
            "/internal/v1/integration/audit/query",
            payload,
        )
        try:
            if (
                type(data["count"]) is not int
                or data["count"] < 0
                or not isinstance(data["results"], list)
                or len(data["results"]) > 100
            ):
                raise ValueError()
            previous = sortkey(before) if before is not None else None
            for row in data["results"]:
                for field in ("id", "organization_id", "request_id"):
                    UUID(row[field])
                if row["organization_id"] not in allowed:
                    raise ValueError("Foreign audit organization")
                if not row["action"].startswith("imports.") or not isinstance(
                    row["context"], dict
                ):
                    raise ValueError()
                current = sortkey(row)
                if previous is not None and current >= previous:
                    raise ValueError("Non-monotonic journal cursor")
                previous = current
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ServiceUnavailable()
        return data

    remote = fetch()
    total = local.count() + remote["count"]
    size = settings.REST_FRAMEWORK.get("PAGE_SIZE", 50)
    if raw == "last":
        number = max(1, (total + size - 1) // size)
    if number > max(1, (total + size - 1) // size):
        raise NotFound("Page invalide.")
    start, end = (number - 1) * size, min(number * size, total)
    local_rows = iter(
        local.values(
            "id",
            "occurred_at",
            "actor_id",
            "organization_id",
            "action",
            "target_id",
            "result",
            "request_id",
            "context",
        ).iterator(chunk_size=100)
    )
    left = next(local_rows, None)
    remote_rows, remote_offset, pos = remote["results"], 0, 0
    output = []
    for index in range(end):
        if (
            pos >= len(remote_rows)
            and remote_offset + len(remote_rows) < remote["count"]
        ):
            remote_offset += len(remote_rows)
            remote_rows, pos = fetch(remote_rows[-1])["results"], 0
            if not remote_rows:
                raise ServiceUnavailable(
                    "Journal modifié pendant la lecture ; réessayer."
                )
        right = remote_rows[pos] if pos < len(remote_rows) else None
        if left is not None and (right is None or sortkey(left) >= sortkey(right)):
            selected, left = left, next(local_rows, None)
        elif right is not None:
            selected = right
            pos += 1
        else:
            raise ServiceUnavailable("Journal modifié pendant la lecture ; réessayer.")
        if index >= start:
            output.append(selected)
    url = request.build_absolute_uri()
    next_url = replace_query_param(url, "page", number + 1) if end < total else None
    previous = (
        (
            remove_query_param(url, "page")
            if number == 2
            else replace_query_param(url, "page", number - 1)
        )
        if number > 1
        else None
    )
    from .views import AuditSerializer

    return Response(
        {
            "count": total,
            "next": next_url,
            "previous": previous,
            "results": AuditSerializer(output, many=True).data,
        }
    )


def sortkey(row):
    value = row["occurred_at"]
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone required")
    return value, UUID(str(row["id"])).int
