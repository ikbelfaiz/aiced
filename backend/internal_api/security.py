import hashlib
import hmac
import re
import secrets
import time
from datetime import timedelta
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied


def signature(secret, key_id, audience, timestamp, nonce, path, body):
    canonical = "\n".join(
        [
            "aiced-internal-v1",
            key_id,
            audience,
            timestamp,
            nonce,
            "POST",
            path,
            hashlib.sha256(body).hexdigest(),
        ]
    )
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def signed_headers(key_id, secret, audience, path, body):
    stamp, nonce = str(int(time.time())), secrets.token_hex(24)
    return {
        "Content-Type": "application/json",
        "X-Aiced-Key-ID": key_id,
        "X-Aiced-Audience": audience,
        "X-Aiced-Time": stamp,
        "X-Aiced-Nonce": nonce,
        "X-Aiced-Signature": signature(
            secret, key_id, audience, stamp, nonce, path, body
        ),
    }


def authenticate(request, audience):
    from django.apps import apps

    InternalNonce = apps.get_model(
        getattr(settings, "INTERNAL_NONCE_MODEL", "identity.InternalNonce")
    )

    if request.method != "POST" or request.META.get("QUERY_STRING"):
        raise PermissionDenied("Appel interne invalide.")
    headers = request.headers
    key_id = headers.get("X-Aiced-Key-ID", "")
    key = settings.AICED_INTERNAL_KEYS.get(key_id)
    stamp, nonce = headers.get("X-Aiced-Time", ""), headers.get("X-Aiced-Nonce", "")
    supplied = headers.get("X-Aiced-Signature", "")
    if (
        not key
        or audience not in key["audiences"]
        or headers.get("X-Aiced-Audience") != audience
        or not re.fullmatch(r"[0-9]{1,12}", stamp)
        or not re.fullmatch(r"[a-f0-9]{48}", nonce)
        or not re.fullmatch(r"[a-f0-9]{64}", supplied)
        or abs(time.time() - int(stamp)) > 30
    ):
        raise PermissionDenied("Authentification interne refusée.")
    body = request.body
    if len(body) > 65536:
        raise PermissionDenied("Appel interne trop volumineux.")
    expected = signature(
        key["secret"], key_id, audience, stamp, nonce, request.path, body
    )
    if not hmac.compare_digest(expected, supplied):
        raise PermissionDenied("Signature interne invalide.")
    # Committed replay protection shared across listener processes; no in-memory cache.
    digest = hashlib.sha256((key_id + ":" + nonce).encode()).hexdigest()
    try:
        with transaction.atomic():
            InternalNonce.objects.create(
                digest=digest, expires_at=timezone.now() + timedelta(seconds=65)
            )
    except IntegrityError:
        raise PermissionDenied("Appel interne déjà consommé.")
    return key["service"]
