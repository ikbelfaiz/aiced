"""Explicit real-Nginx integration suite: `manage.py test gateway_tests`."""

import hashlib
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time
from urllib.parse import quote, urlsplit
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import transaction
from django.test import LiveServerTestCase, SimpleTestCase, override_settings
from django.utils import timezone
from contracts.tests import ConsumerContractChecks
from testing.fixtures import PASSWORD
from testing.gateway import nginx_gateway, free_port


class HTTPClient:
    """Small APIClient-compatible adapter: all requests cross a real TCP proxy."""

    def __init__(self, base):
        self.base = urlsplit(base)
        self.cookies = SimpleCookie()
        self.headers = {}

    def credentials(self, **kwargs):
        self.headers = {
            k.removeprefix("HTTP_").replace("_", "-"): v for k, v in kwargs.items()
        }

    def force_login(self, user):
        # Deliberately authenticate over HTTP instead of installing a test session.
        self.cookies = SimpleCookie()
        self.credentials(HTTP_X_CSRFTOKEN=self.get("/api/auth/csrf/").data["csrfToken"])
        response = self.post(
            "/api/auth/login/",
            {"username": user.username, "password": PASSWORD},
            format="json",
        )
        if response.status_code != 200:
            raise AssertionError(response.data)

    def request(
        self, method, path, data=None, format=None, content_type=None, **headers
    ):
        if format == "json":
            data = json.dumps(data).encode()
            content_type = "application/json"
        if data is None:
            data = b"" if method in ["POST", "PATCH"] else None
        if isinstance(data, str):
            data = data.encode()
        outgoing = {**self.headers, **headers}
        outgoing["Cookie"] = self.cookies.output(header="", sep=";").strip()
        if content_type:
            outgoing["Content-Type"] = content_type
        connection = HTTPConnection(self.base.hostname, self.base.port, timeout=15)
        try:
            connection.request(method, quote(path, safe="/?=&%:+"), data, outgoing)
            response = connection.getresponse()
            content = response.read()
            for name, value in response.getheaders():
                if name.lower() == "set-cookie":
                    self.cookies.load(value)

            class Result(dict):
                pass

            result = Result(response.getheaders())
            result.status_code = response.status
            result.content = content
            try:
                result.data = json.loads(content)
            except (ValueError, UnicodeDecodeError):
                result.data = None
            result.json = lambda: result.data
            return result
        finally:
            connection.close()

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, data=None, **kwargs):
        return self.request("POST", path, data, **kwargs)

    def patch(self, path, data=None, **kwargs):
        return self.request("PATCH", path, data, **kwargs)


class FixtureLiveServer(LiveServerTestCase):
    host = "127.0.0.1"  # Avoid localhost resolving to an unbound IPv6 listener.

    @classmethod
    def setUpTestData(cls):
        pass  # TransactionTestCase fixtures are recreated per test, not atomically.


@override_settings(
    AICED_GATEWAY_KEY="synthetic-gateway-key-" + "x" * 40,
    STATIC_URL="/static/",
    ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"],
)
class GatewayContracts(ConsumerContractChecks, FixtureLiveServer):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.directory = tempfile.TemporaryDirectory(prefix="aiced-gateway-")
        cls.proxy = nginx_gateway(
            Path(cls.directory.name),
            cls.live_server_url.removeprefix("http://"),
            cls.live_server_url.removeprefix("http://"),
            settings.AICED_GATEWAY_KEY,
        )
        try:
            cls.gateway_url = cls.proxy.__enter__()
        except Exception:
            cls.directory.cleanup()
            super().tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            cls.proxy.__exit__(None, None, None)
            cls.directory.cleanup()
        finally:
            super().tearDownClass()

    def setUp(self):
        # Deferred subtype constraints require Party + subtype in one commit.
        with transaction.atomic():
            self.setUpTestData()
        super().setUp()
        self.client = HTTPClient(self.gateway_url)

    def test_csrf_rotation_origin_spoofing_logout_and_direct_rollback(self):
        self.assertEqual(
            self.client.post("/api/auth/login/", {}, format="json").status_code, 403
        )
        before_login = self.client.get("/api/auth/csrf/").data["csrfToken"]
        self.login_as(self.reader)
        self.client.credentials(HTTP_X_CSRFTOKEN=before_login)
        self.assertEqual(
            self.client.patch(
                f"/api/clients/{self.own.pk}/crm/",
                {"notes": "SYNTHETIC stale csrf"},
                format="json",
            ).status_code,
            403,
        )
        self.client.credentials(
            HTTP_X_CSRFTOKEN=self.client.get("/api/auth/csrf/").data["csrfToken"]
        )
        self.assertEqual(
            self.client.patch(
                f"/api/clients/{self.own.pk}/crm/",
                {"notes": "SYNTHETIC current csrf"},
                format="json",
                Origin=self.gateway_url,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/clients/{self.own.pk}/crm/",
                {"notes": "synthetic"},
                format="json",
                Origin="https://evil.invalid",
            ).status_code,
            403,
        )
        # Headers claiming a different user or forwarding metadata confer no rights.
        response = self.client.get(
            f"/api/clients/{self.other_org_hidden.pk}/workspace/",
            **{
                "X-User-ID": str(self.manager.pk),
                "X-Forwarded-For": "198.51.100.99",
                "X-Aiced-Gateway-Key": "forged",
                "X-Aiced-Proto": "https",
            },
        )
        self.assertEqual(response.status_code, 404)
        # Cookie and CSRF survive a rollback at the SAME public origin (Host).
        direct = HTTPClient(self.live_server_url)
        direct.cookies = self.client.cookies
        direct.headers = {
            **self.client.headers,
            "Host": urlsplit(self.gateway_url).netloc,
        }
        self.assertEqual(direct.get("/api/session/").data["id"], str(self.reader.pk))
        self.assertEqual(
            direct.patch(
                f"/api/clients/{self.own.pk}/crm/",
                {"notes": "SYNTHETIC rollback"},
                format="json",
                Origin=self.gateway_url,
            ).status_code,
            200,
        )
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 204)
        self.assertEqual(direct.get("/api/session/").status_code, 403)

    def test_real_account_and_ip_login_limits_ignore_forged_ip(self):
        self.client.credentials(
            HTTP_X_CSRFTOKEN=self.client.get("/api/auth/csrf/").data["csrfToken"]
        )
        for index in range(settings.LOGIN_ACCOUNT_LIMIT):
            self.assertEqual(
                self.client.post(
                    "/api/auth/login/",
                    {"username": "synthetic.missing", "password": PASSWORD},
                    format="json",
                ).status_code,
                400,
            )
        response = self.client.post(
            "/api/auth/login/",
            {"username": "synthetic.missing", "password": PASSWORD},
            format="json",
            **{"X-Forwarded-For": "192.0.2.1"},
        )
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)
        # Remaining attempts share the actual peer IP even with forged metadata.
        for index in range(settings.LOGIN_IP_LIMIT - settings.LOGIN_ACCOUNT_LIMIT - 1):
            self.assertEqual(
                self.client.post(
                    "/api/auth/login/",
                    {"username": f"synthetic.missing{index}", "password": PASSWORD},
                    format="json",
                    **{"X-Aiced-Client-IP": f"192.0.2.{index+1}"},
                ).status_code,
                400,
            )
        self.assertEqual(
            self.client.post(
                "/api/auth/login/",
                {"username": "synthetic.final", "password": PASSWORD},
                format="json",
            ).status_code,
            429,
        )

    def test_expired_session_json_limits_and_preserved_backend_errors(self):
        self.login_as(self.reader)
        response = self.client.patch(
            f"/api/clients/{self.own.pk}/crm/",
            b"{" + b" " * 65536,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.data["error"]["status"], 413)
        Session.objects.update(
            expire_date=timezone.now() - timezone.timedelta(seconds=1)
        )
        self.assertEqual(self.client.get("/api/session/").status_code, 403)


class GatewayTransportTests(SimpleTestCase):
    """Echo upstream proves every frozen route/method is forwarded unchanged."""

    def test_all_routes_bytes_cookies_headers_errors_timeouts_and_no_retry(self):
        captured = []

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_request(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                captured.append((self.command, self.path, body, dict(self.headers)))
                if self.path == "/api/slow/":
                    time.sleep(2)
                status = 409 if self.path == "/api/conflict/" else 200
                self.send_response(status)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header(
                    "Set-Cookie", "sessionid=synthetic; HttpOnly; SameSite=Lax; Path=/"
                )
                self.send_header(
                    "Content-Disposition", 'attachment; filename="synthetic.csv"'
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    self.wfile.write(body or b"synthetic-upstream")
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

            do_GET = do_POST = do_PATCH = do_DELETE = handle_request

        server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory(
                prefix="aiced-gateway-transport-"
            ) as directory:
                key = secrets.token_urlsafe(48)
                with nginx_gateway(
                    directory,
                    f"127.0.0.1:{server.server_port}",
                    f"127.0.0.1:{server.server_port}",
                    key,
                    timeout=1,
                ) as base:
                    client = HTTPClient(base)
                    manifest = json.loads(
                        (
                            settings.BASE_DIR / "contracts/public-api-baseline.json"
                        ).read_text()
                    )
                    for route in manifest["routes"]:
                        path = (
                            re.sub(
                                r"<uuid:\w+>",
                                "00000000-0000-0000-0000-000000000001",
                                route["path"],
                            )
                            + "?search=a%2Bb&page=2"
                        )
                        for method in route["methods"]:
                            with self.subTest(path=path, method=method):
                                response = client.request(
                                    method,
                                    path,
                                    b"\x00synthetic\xff",
                                    content_type="application/octet-stream",
                                    **{
                                        "X-Forwarded-For": "forged",
                                        "X-Aiced-Gateway-Key": "forged",
                                        "Origin": base,
                                    },
                                )
                                self.assertEqual(response.status_code, 200)
                                self.assertEqual(
                                    captured[-1][:3],
                                    (method, path, b"\x00synthetic\xff"),
                                )
                                headers = {
                                    k.lower(): v for k, v in captured[-1][3].items()
                                }
                                self.assertEqual(headers["host"], urlsplit(base).netloc)
                                self.assertEqual(headers["origin"], base)
                                self.assertEqual(headers["x-aiced-gateway-key"], key)
                                self.assertEqual(
                                    headers["x-aiced-client-ip"], "127.0.0.1"
                                )
                                self.assertNotIn("x-forwarded-for", headers)
                                self.assertEqual(
                                    response["Content-Disposition"],
                                    'attachment; filename="synthetic.csv"',
                                )
                                self.assertTrue(client.cookies["sessionid"]["httponly"])
                    payload = b"\x00" * (10 * 1024 * 1024)
                    response = client.post(
                        "/api/imports/synthetic/upload/",
                        payload,
                        content_type="application/octet-stream",
                    )
                    self.assertEqual(
                        hashlib.sha256(response.content).digest(),
                        hashlib.sha256(payload).digest(),
                    )
                    count = len(captured)
                    response = client.post(
                        "/api/imports/synthetic/upload/",
                        payload + b"X",
                        content_type="application/octet-stream",
                    )
                    self.assertEqual(response.status_code, 413)
                    self.assertEqual(response.data["error"]["status"], 413)
                    self.assertEqual(response["Cache-Control"], "no-store")
                    self.assertEqual(len(captured), count)
                    self.assertEqual(
                        client.post("/api/conflict/", b"synthetic").status_code, 409
                    )
                    count = len(captured)
                    response = client.post("/api/slow/", b"synthetic")
                    self.assertEqual(response.status_code, 504)
                    self.assertEqual(response.data["error"]["status"], 504)
                    self.assertEqual(len(captured), count + 1)
                with nginx_gateway(
                    Path(directory) / "offline",
                    f"127.0.0.1:{free_port()}",
                    f"127.0.0.1:{server.server_port}",
                    key,
                ) as base:
                    response = HTTPClient(base).post("/api/health/", b"synthetic")
                    self.assertEqual(response.status_code, 502)
                    self.assertEqual(response.data["error"]["status"], 502)
                    self.assertEqual(response["Cache-Control"], "no-store")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
