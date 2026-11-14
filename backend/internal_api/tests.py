"""Private contracts over real HTTP plus PostgreSQL transaction/race tests."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
import json
import threading
import time
from unittest.mock import patch
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import connection, connections, transaction, IntegrityError
from django.middleware.csrf import get_token
from django.test import LiveServerTestCase, RequestFactory, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient
from audit.models import AuditEvent, AuditOutbox, AuditReceipt
from audit.services import record
from audit.delivery import deliver, envelope
from clients.models import CRMProfile
from clients.services import update_crm
from identity.models import User, RoleAssignment
from identity.coordination import barrier, remote_write
from testing.fixtures import SecurityFixtures
from .client import InternalClient, ServiceUnavailable
from .security import signed_headers

KEY = "synthetic-internal-signing-key-" + "x" * 40
KEYS = {
    "client-v1": {
        "secret": KEY,
        "service": "client_crm",
        "audiences": ["iam", "audit"],
    },
    "commercial-v1": {
        "secret": KEY + "c",
        "service": "commercial",
        "audiences": ["iam", "client", "audit"],
    },
    "integration-v1": {
        "secret": KEY + "i",
        "service": "integration",
        "audiences": ["iam", "audit"],
    },
}


class FixtureServer(LiveServerTestCase):
    host = "127.0.0.1"

    @classmethod
    def setUpTestData(cls):
        pass


@override_settings(
    ROOT_URLCONF="internal_api.urls",
    STATIC_URL="/static/",
    ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"],
    AICED_INTERNAL_KEYS=KEYS,
)
class InternalContracts(SecurityFixtures, FixtureServer):
    def required_audit(self, decision, result):
        return record(
            "clients.synthetic", actor=User.objects.get(pk=decision["actor_id"])
        )

    def setUp(self):
        with transaction.atomic():
            self.setUpTestData()
        super().setUp()
        browser = APIClient(enforce_csrf_checks=True)
        browser.force_login(self.reader)
        self.session_key = browser.cookies["sessionid"].value
        request = RequestFactory().get("/")
        token = get_token(request)
        self.credentials = {
            "session_key": self.session_key,
            "method": "GET",
            "host": "127.0.0.1",
            "scheme": "http",
            "csrf_cookie": request.META["CSRF_COOKIE"],
            "csrf_token": token,
            "origin": "http://127.0.0.1",
        }
        self.rpc = InternalClient(self.live_server_url, "client-v1", KEY, "iam")
        self.payload = {
            "credentials": self.credentials,
            "organization_id": str(self.org_a.pk),
            "capabilities": ["clients.update_crm"],
        }

    def raw(self, path, payload, headers=None):
        import http.client
        from urllib.parse import urlsplit

        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        connection = http.client.HTTPConnection(
            urlsplit(self.live_server_url).hostname,
            urlsplit(self.live_server_url).port,
            timeout=5,
        )
        try:
            connection.request("POST", path, body, headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_forged_unsigned_tampered_replayed_expired_or_wrong_audience_requests(self):
        path = "/internal/v1/principal/resolve"
        payload = {"credentials": self.credentials}
        self.assertEqual(
            self.raw(
                path, payload, {"X-User-ID": str(self.manager.pk), "X-Role": "admin"}
            )[0],
            403,
        )
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        headers = signed_headers("client-v1", KEY, "iam", path, body)
        headers["X-User-ID"] = str(self.manager.pk)
        status, raw = self.raw(path, payload, headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["actor_id"], str(self.reader.pk))
        self.assertEqual(self.raw(path, payload, headers)[0], 403)
        headers = signed_headers("client-v1", KEY, "iam", path, body)
        self.assertEqual(
            self.raw(
                path, {"credentials": {**self.credentials, "method": "POST"}}, headers
            )[0],
            403,
        )
        headers = signed_headers("client-v1", KEY, "audit", path, body)
        self.assertEqual(self.raw(path, payload, headers)[0], 403)
        with patch("internal_api.security.time.time", return_value=time.time() - 90):
            headers = signed_headers("client-v1", KEY, "iam", path, body)
        self.assertEqual(self.raw(path, payload, headers)[0], 403)

    def test_scope_privilege_escalation_csrf_and_extra_fields_are_denied(self):
        decision = self.rpc.authorize(self.payload)
        self.assertEqual({g["scope"] for g in decision["grants"]}, {"assigned"})
        self.assertEqual(decision["actor_id"], str(self.reader.pk))
        for capabilities, org in [
            (["users.manage"], self.org_a),
            (["clients.view_financial"], self.org_a),
            (["clients.update_crm"], self.org_b),
        ]:
            with self.assertRaises(PermissionDenied):
                self.rpc.authorize(
                    {
                        **self.payload,
                        "capabilities": capabilities,
                        "organization_id": str(org.pk),
                    }
                )
        valid = {**self.payload, "credentials": {**self.credentials, "method": "POST"}}
        self.assertTrue(self.rpc.authorize(valid)["authorized"])
        for change in [{"csrf_token": "forged"}, {"origin": "https://evil.invalid"}]:
            with self.assertRaises(PermissionDenied):
                self.rpc.authorize(
                    {**valid, "credentials": {**valid["credentials"], **change}}
                )
        # Arbitrary actor or role cannot be injected even in a signed body.
        self.assertEqual(self.raw("/internal/v1/authorization/check", {})[0], 403)
        with self.assertRaises(ServiceUnavailable):
            self.rpc.post(
                "/internal/v1/authorization/check",
                {**self.payload, "actor_id": str(self.manager.pk)},
            )

    def test_client_owns_object_scoping_and_service_capability_boundary(self):
        from testing.fixtures import role

        RoleAssignment.objects.create(
            membership=self.reader_m,
            role=role("synthetic-opps", ["opportunities.view", "opportunities.manage"]),
            scope="assigned",
        )
        rpc = InternalClient(self.live_server_url, "commercial-v1", KEY + "c", "client")
        payload = {
            "credentials": self.credentials,
            "party_id": str(self.own.pk),
            "capability": "opportunities.manage",
        }
        self.assertTrue(
            rpc.post("/internal/v1/clients/authorize", payload)["authorized"]
        )
        for party in [self.same_org_hidden, self.other_org_hidden]:
            with self.assertRaises(PermissionDenied):
                rpc.post(
                    "/internal/v1/clients/authorize",
                    {**payload, "party_id": str(party.pk)},
                )
        wrong = InternalClient(self.live_server_url, "client-v1", KEY, "client")
        with self.assertRaises(PermissionDenied):
            wrong.post("/internal/v1/clients/authorize", payload)

    def test_live_user_password_session_membership_org_and_permission_revocation(self):
        self.assertTrue(self.rpc.authorize(self.payload)["authorized"])
        cases = [
            (
                User.objects.filter(pk=self.reader.pk),
                {"is_active": False},
                {"is_active": True},
            ),
            (
                RoleAssignment.objects.filter(pk=self.reader_grant.pk),
                {"is_active": False},
                {"is_active": True},
            ),
            (
                type(self.reader_m).objects.filter(pk=self.reader_m.pk),
                {"is_active": False},
                {"is_active": True},
            ),
            (
                type(self.org_a).objects.filter(pk=self.org_a.pk),
                {"is_active": False},
                {"is_active": True},
            ),
            (
                RoleAssignment.objects.filter(pk=self.reader_grant.pk),
                {"expires_at": timezone.now() - timedelta(seconds=1)},
                {"expires_at": None},
            ),
        ]
        for queryset, change, undo in cases:
            queryset.update(**change)
            with self.assertRaises(PermissionDenied):
                self.rpc.authorize(self.payload)
            queryset.update(**undo)
        old_password = self.reader.password
        self.reader.set_password("SYNTHETIC new password")
        self.reader.save(update_fields=["password"])
        with self.assertRaises(PermissionDenied):
            self.rpc.authorize(self.payload)
        User.objects.filter(pk=self.reader.pk).update(password=old_password)
        Session.objects.filter(session_key=self.session_key).delete()
        with self.assertRaises(PermissionDenied):
            self.rpc.authorize(self.payload)

    def test_audit_and_outbox_failures_roll_back_business_change(self):
        before = AuditEvent.objects.count()
        for target in [
            "audit.services.AuditEvent.objects.create",
            "audit.services.AuditOutbox.objects.create",
        ]:
            with patch(target, side_effect=RuntimeError("synthetic audit failure")):
                with self.assertRaises(RuntimeError):
                    update_crm(
                        self.reader, self.own.pk, {"notes": "SYNTHETIC must roll back"}
                    )
            self.assertEqual(CRMProfile.objects.get(party=self.own).notes, "")
            self.assertEqual(AuditEvent.objects.count(), before)
            self.assertEqual(AuditOutbox.objects.count(), 0)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                record("clients.synthetic", actor=self.reader)
                raise RuntimeError("synthetic business failure")
        self.assertEqual(AuditEvent.objects.count(), before)

    def test_deactivation_requires_delegable_scope_and_rolls_back_on_audit_failure(
        self,
    ):
        from identity.services import deactivate_user

        with self.assertRaises(PermissionDenied):
            deactivate_user(self.it, self.reader.pk)
        with patch(
            "audit.services.AuditOutbox.objects.create",
            side_effect=RuntimeError("synthetic audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                deactivate_user(self.manager, self.reader.pk)
        self.assertTrue(User.objects.get(pk=self.reader.pk).is_active)
        deactivate_user(self.manager, self.reader.pk)
        with self.assertRaises(PermissionDenied):
            self.rpc.authorize(self.payload)

    def test_remote_required_audit_failure_rolls_back_change(self):
        with self.assertRaises(RuntimeError):
            remote_write(
                lambda: self.rpc.authorize(self.payload),
                lambda decision: CRMProfile.objects.filter(party=self.own).update(
                    notes="SYNTHETIC rollback"
                ),
                lambda decision, result: None,
            )
        self.assertEqual(CRMProfile.objects.get(party=self.own).notes, "")

    def test_outbox_delivery_retries_deduplicates_and_conflicts_are_rejected(self):
        event = record(
            "clients.synthetic", actor=self.reader, context={"notes": "NEVER SENT"}
        )
        rpc = InternalClient(self.live_server_url, "client-v1", KEY, "audit")
        with patch.object(rpc, "post", side_effect=ServiceUnavailable()):
            with self.assertRaises(ServiceUnavailable):
                deliver(event.pk, rpc)
        self.assertIsNone(AuditOutbox.objects.get(pk=event.pk).delivered_at)
        # Crash/ambiguous timeout after server receipt, before local acknowledgment.
        payload = envelope(event)
        self.assertTrue(rpc.post("/internal/v1/audit/events", payload)["accepted"])
        deliver(event.pk, rpc)
        self.assertEqual(AuditReceipt.objects.count(), 1)
        self.assertNotIn("NEVER SENT", json.dumps(AuditReceipt.objects.get().payload))
        self.assertIsNotNone(AuditOutbox.objects.get(pk=event.pk).delivered_at)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AuditOutbox.objects.filter(pk=event.pk).update(producer="iam")
        with self.assertRaises(ServiceUnavailable):
            rpc.post("/internal/v1/audit/events", {**payload, "result": "denied"})
        with self.assertRaises(PermissionDenied):
            rpc.post(
                "/internal/v1/audit/events", {**payload, "action": "users.deactivated"}
            )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AuditReceipt.objects.all().update(digest="x" * 64)

    def wait_blocked(self, pid, finished):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT cardinality(pg_blocking_pids(%s))>0", [pid])
                if cursor.fetchone()[0]:
                    return
            if finished.done():
                break
            time.sleep(0.01)
        self.fail("Expected transaction to wait on the revocation barrier")

    def test_waiting_remote_writer_rechecks_revocation_over_http(self):
        ready = threading.Event()
        pids = []

        def worker():
            try:
                connection.ensure_connection()
                pids.append(connection.connection.info.backend_pid)
                ready.set()
                return remote_write(
                    lambda: self.rpc.authorize(self.payload),
                    lambda decision: CRMProfile.objects.filter(
                        party_id=self.own.pk
                    ).update(notes="forbidden"),
                    self.required_audit,
                )
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                barrier(exclusive=True)
                future = executor.submit(worker)
                self.assertTrue(ready.wait(5))
                self.wait_blocked(pids[0], future)
                RoleAssignment.objects.filter(pk=self.reader_grant.pk).update(
                    is_active=False
                )
            with self.assertRaises(PermissionDenied):
                future.result(timeout=8)
        self.assertEqual(CRMProfile.objects.get(party=self.own).notes, "")

    def test_deactivation_waits_for_admitted_write_commit_then_denies_new_writes(self):
        admitted = threading.Event()
        release = threading.Event()
        revoke_ready = threading.Event()
        pids = []

        def writer():
            try:

                def change(decision):
                    admitted.set()
                    if not release.wait(8):
                        raise RuntimeError("Synthetic test release timeout")
                    CRMProfile.objects.filter(party_id=self.own.pk).update(
                        notes="SYNTHETIC admitted"
                    )

                remote_write(
                    lambda: self.rpc.authorize(self.payload),
                    change,
                    self.required_audit,
                )
            finally:
                connections.close_all()

        def revoke():
            try:
                connection.ensure_connection()
                pids.append(connection.connection.info.backend_pid)
                revoke_ready.set()
                User.objects.filter(pk=self.reader.pk).update(is_active=False)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            write_future = executor.submit(writer)
            try:
                self.assertTrue(admitted.wait(5))
                revoke_future = executor.submit(revoke)
                self.assertTrue(revoke_ready.wait(5))
                self.wait_blocked(pids[0], revoke_future)
            finally:
                release.set()
            write_future.result(timeout=8)
            revoke_future.result(timeout=8)
        self.assertEqual(
            CRMProfile.objects.get(party=self.own).notes, "SYNTHETIC admitted"
        )
        self.assertEqual(AuditOutbox.objects.count(), 1)
        with self.assertRaises(PermissionDenied):
            remote_write(
                lambda: self.rpc.authorize(self.payload),
                lambda result: self.fail("Revoked write ran"),
                self.required_audit,
            )

    def test_service_failure_and_malformed_success_fail_closed_and_roll_back(self):
        with self.assertRaises(PermissionDenied):
            remote_write(
                lambda: {"authorized": False},
                lambda decision: self.fail("False decision admitted a write"),
                self.required_audit,
            )
        with patch.object(self.rpc, "post", return_value={"authorized": True}):
            with self.assertRaises(ServiceUnavailable):
                self.rpc.authorize(self.payload)
        from testing.gateway import free_port

        offline = InternalClient(
            f"http://127.0.0.1:{free_port()}", "client-v1", KEY, "iam", timeout=0.2
        )
        with self.assertRaises(ServiceUnavailable):
            remote_write(
                lambda: offline.authorize(self.payload),
                lambda decision: self.fail("Unavailable IAM admitted write"),
                self.required_audit,
            )
        self.assertEqual(CRMProfile.objects.get(party=self.own).notes, "")
        with self.assertRaises(ValueError):
            InternalClient("http://untrusted.invalid", "client-v1", KEY, "iam")

    def test_public_urlconf_does_not_expose_internal_routes_or_trust_headers(self):
        with override_settings(ROOT_URLCONF="config.urls"):
            browser = APIClient()
            self.assertEqual(
                browser.post("/internal/v1/authorization/check", {}).status_code, 404
            )
            self.assertEqual(
                browser.get(
                    "/api/clients/",
                    HTTP_X_USER_ID=str(self.manager.pk),
                    HTTP_X_ROLE="admin",
                ).status_code,
                403,
            )
