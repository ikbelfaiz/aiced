"""Pairwise signed HTTP, fresh identity, Client-owned object authorization."""

from dataclasses import dataclass
from uuid import UUID
import re
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import PermissionDenied
from internal_api.client import InternalClient, ServiceUnavailable, request_credentials


@dataclass
class Actor:
    id: UUID
    username: str
    credentials: dict
    is_authenticated = True

    @property
    def pk(self):
        return self.id


def peer(kind):
    ident = (
        settings.COMMERCIAL_IAM_KEY_ID
        if kind == "iam"
        else settings.COMMERCIAL_CLIENT_KEY_ID
    )
    return InternalClient(
        settings.IAM_URL if kind == "iam" else settings.CLIENT_URL,
        ident,
        settings.AICED_INTERNAL_KEYS[ident]["secret"],
        kind,
        preserve_not_found=kind == "client",
    )


def principal(credentials, timeout=3):
    client = peer("iam")
    client.timeout = timeout
    data = client.post(
        "/internal/v1/grants/snapshot", {"credentials": credentials}
    )
    try:
        ident = UUID(data["actor_id"])
        if (
            not isinstance(data["username"], str)
            or not 0 < len(data["username"]) <= 150
            or not isinstance(data["grants"], list)
            or len(data["grants"]) > 1000
        ):
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise ServiceUnavailable()
    return Actor(ident, data["username"], credentials), data


def authorize(actor, party_id, capability):
    data = peer("client").post(
        "/internal/v1/clients/authorize",
        {
            "credentials": actor.credentials,
            "party_id": str(party_id),
            "capability": capability,
        },
    )
    try:
        if (
            data["authorized"] is not True
            or UUID(data["actor_id"]) != actor.pk
            or UUID(data["party_id"]) != UUID(str(party_id))
            or type(data["version"]) is not int
            or data["version"] < 1
        ):
            raise ValueError()
        UUID(data["organization_id"])
    except (KeyError, TypeError, ValueError):
        raise ServiceUnavailable()
    return data


class DelegatedSession(BaseAuthentication):
    def authenticate(self, request):
        if not re.fullmatch(
            r"[a-z0-9]{32}", request.COOKIES.get(settings.SESSION_COOKIE_NAME, "")
        ):
            return None
        actor, _ = principal(request_credentials(request))
        return actor, None
