"""Bounded synchronous HTTP, no redirects/retries or cached decisions."""

import http.client
import json
import socket
import threading
from urllib.parse import urlsplit
from rest_framework.exceptions import APIException
from .security import signed_headers


def request_credentials(request):
    from django.conf import settings

    return {
        "session_key": request.COOKIES.get(settings.SESSION_COOKIE_NAME, ""),
        "method": request.method,
        "csrf_cookie": request.COOKIES.get(settings.CSRF_COOKIE_NAME, ""),
        "csrf_token": request.headers.get("X-CSRFToken", ""),
        "origin": request.headers.get("Origin", ""),
        "referer": request.headers.get("Referer", ""),
        "host": request.get_host(),
        "scheme": request.scheme,
    }


class ServiceUnavailable(APIException):
    status_code = 503
    default_detail = "Service d’autorisation indisponible."


class InternalClient:
    def __init__(self, url, key_id, secret, audience, timeout=3, preserve_not_found=False):
        self.url, self.key_id, self.secret, self.audience = (
            urlsplit(url),
            key_id,
            secret,
            audience,
        )
        self.preserve_not_found = preserve_not_found
        self.timeout = timeout
        if (
            self.url.username
            or self.url.password
            or self.url.path not in ("", "/")
            or self.url.query
            or self.url.fragment
            or self.url.scheme not in ("http", "https")
        ):
            raise ValueError("Invalid internal service URL")
        if self.url.scheme == "http" and self.url.hostname not in (
            "localhost",
            "127.0.0.1",
            "::1",
        ):
            raise ValueError(
                "Internal HTTP is limited to loopback; use HTTPS between hosts"
            )

    def post(self, path, payload):
        from time import monotonic
        from core.request_metrics import record
        started = monotonic()
        peer_request_id = None
        status = None
        if not path.startswith("/internal/v1/") or "?" in path:
            raise ValueError("Invalid internal contract path")
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        if len(body) > 65536:
            raise ValueError("Internal payload exceeds limit")
        cls = (
            http.client.HTTPSConnection
            if self.url.scheme == "https"
            else http.client.HTTPConnection
        )
        conn = cls(self.url.hostname, self.url.port, timeout=self.timeout)
        # Bound a peer that keeps a response alive by slowly dripping bytes.
        # DNS/connect also retain their ordinary socket/connect timeout; no retries.
        expired = threading.Event()
        transport = [None]

        def cancel():
            expired.set()
            active = transport[0] or conn.sock
            if active is not None:
                try:
                    active.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        deadline = threading.Timer(self.timeout, cancel)
        deadline.daemon = True
        deadline.start()
        try:
            conn.request(
                "POST",
                path,
                body,
                signed_headers(self.key_id, self.secret, self.audience, path, body),
            )
            transport[0] = conn.sock
            if expired.is_set():
                raise ServiceUnavailable()
            response = conn.getresponse()
            status = response.status
            peer_request_id = response.getheader('X-Request-ID')
            raw = response.read(65537)
            if expired.is_set():
                raise ServiceUnavailable()
            if len(raw) > 65536 or response.status != 200:
                # Denials never yield an authorization decision or actor fallback.
                from rest_framework.exceptions import PermissionDenied

                if response.status == 404 and self.preserve_not_found:
                    from rest_framework.exceptions import NotFound
                    raise NotFound()
                if response.status in (401, 403, 404):
                    raise PermissionDenied("Autorisation interne refusée.")
                raise ServiceUnavailable()
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ServiceUnavailable()
            return result
        except (OSError, http.client.HTTPException, ValueError) as error:
            raise ServiceUnavailable() from error
        finally:
            deadline.cancel()
            conn.close()
            record('internal_http', peer=self.audience, path=path,
                   peer_request_id=peer_request_id, status=status,
                   seconds=round(monotonic()-started, 6), timeout_seconds=round(self.timeout, 6),
                   expired=expired.is_set())

    def authorize(self, payload):
        result = self.post("/internal/v1/authorization/check", payload)
        from uuid import UUID

        try:
            UUID(result["actor_id"])
            if result.get("authorized") is not True or result["organization_id"] != str(
                payload["organization_id"]
            ):
                raise ValueError("Mismatched decision")
            rows = result["grants"]
            if not isinstance(rows, list) or not set(payload["capabilities"]) <= {
                row["capability"] for row in rows
            }:
                raise ValueError("Missing grants")
            for row in rows:
                UUID(row["membership_id"])
                if row["scope"] not in ("assigned", "organization"):
                    raise ValueError("Invalid scope")
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ServiceUnavailable()
        return result
