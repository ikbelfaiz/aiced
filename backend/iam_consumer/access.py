"""Fresh signed IAM decisions; Client/Commercial retain their object filtering."""

import re
from uuid import UUID
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import PermissionDenied
from internal_api.client import InternalClient, ServiceUnavailable, request_credentials
from .models import ActorRef, OrganizationRef


def client():
    key = settings.IAM_CONSUMER_KEY_ID
    return InternalClient(
        settings.IAM_URL, key, settings.AICED_INTERNAL_KEYS[key]["secret"], "iam"
    )


def snapshot(credentials):
    data = client().post("/internal/v1/grants/snapshot", {"credentials": credentials})
    try:
        UUID(data["actor_id"])
        if (
            not isinstance(data["username"], str)
            or not 0 < len(data["username"]) <= 150
        ):
            raise ValueError()
        if not isinstance(data["grants"], list) or len(data["grants"]) > 1000:
            raise ValueError()
        if (
            not isinstance(data["organizations"], list)
            or len(data["organizations"]) > 1000
        ):
            raise ValueError()
        orgs = set()
        for row in data["organizations"]:
            UUID(row["id"])
            orgs.add(row["id"])
            if not isinstance(row["name"], str) or len(row["name"]) > 160:
                raise ValueError()
        for row in data["grants"]:
            UUID(row["organization_id"])
            UUID(row["membership_id"])
            if (
                row["organization_id"] not in orgs
                or row["scope"] not in ("assigned", "organization")
                or not isinstance(row["capability"], str)
            ):
                raise ValueError()
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ServiceUnavailable()
    return data


def read_principal(credentials, *, persist=True):
    data = snapshot(credentials)
    if not persist:
        actor = ActorRef(pk=data["actor_id"], username=data["username"])
        actor.credentials = credentials
        actor._iam_grants = data["grants"]
        return actor
    actor, _ = ActorRef.objects.update_or_create(
        pk=data["actor_id"], defaults={"username": data["username"]}
    )
    for row in data["organizations"]:
        OrganizationRef.objects.update_or_create(
            pk=row["id"], defaults={"name": row["name"], "is_active": True}
        )
    actor.credentials = credentials
    actor._iam_grants = data["grants"]
    return actor


class DelegatedSession(BaseAuthentication):
    def authenticate(self, request):
        if not re.fullmatch(
            r"[a-z0-9]{32}", request.COOKIES.get(settings.SESSION_COOKIE_NAME, "")
        ):
            return None
        return read_principal(request_credentials(request)), None


def rows(actor):
    if not actor or not getattr(actor, "credentials", None):
        raise PermissionDenied("Session deleguee obligatoire.")
    # The actor is newly created by authentication for this HTTP request only.
    # Write admission always replaces this snapshot AFTER acquiring the fences.
    if hasattr(actor, "_iam_grants"):
        return actor._iam_grants
    data = snapshot(actor.credentials)
    if str(actor.pk) != data["actor_id"]:
        raise PermissionDenied("Identite incoherente.")
    return data["grants"]


def scope(actor, code):
    current = [row for row in rows(actor) if row["capability"] == code]
    return (
        [
            UUID(row["organization_id"])
            for row in current
            if row["scope"] == "organization"
        ],
        [UUID(row["membership_id"]) for row in current if row["scope"] == "assigned"],
    )


class Values(list):
    def exists(self):
        return bool(self)

    def distinct(self):
        return Values(dict.fromkeys(self))

    def filter(self, **kw):
        if set(kw) != {"membership__organization_id"}:
            raise RuntimeError("Unsupported grant filter")
        return Values(
            v for v in self if str(v) == str(kw["membership__organization_id"])
        )


class GrantRows(list):
    def exists(self):
        return bool(self)

    def filter(self, **kw):
        mapping = {"scope": "scope", "membership__organization_id": "organization_id"}
        if set(kw) - mapping.keys():
            raise RuntimeError("Unsupported grant filter")
        return GrantRows(
            row
            for row in self
            if all(str(row[mapping[k]]) == str(v) for k, v in kw.items())
        )

    def values_list(self, field, flat=False):
        key = {
            "membership__organization_id": "organization_id",
            "membership_id": "membership_id",
        }[field]
        return Values(UUID(r[key]) if flat else (UUID(r[key]),) for r in self)

    def values(self, field):
        return self.values_list(field, flat=True)


def grant_rows(actor, code=None):
    return GrantRows(r for r in rows(actor) if code is None or r["capability"] == code)


def organization_values(actor, code, full_scope):
    current = grant_rows(actor, code)
    if full_scope:
        current = current.filter(scope="organization")
    return current.values_list("membership__organization_id", flat=True)
