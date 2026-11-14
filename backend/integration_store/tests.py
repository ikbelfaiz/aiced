"""No privileged test database is needed; SQL/process tests live in s3_rehearsal."""

import json
import sys
from unittest.mock import patch
from uuid import uuid4
from django.apps import apps
from django.conf import settings
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase
from django.urls import get_resolver
from rest_framework.exceptions import PermissionDenied
from integration_service.access import RemoteAccess
from .models import ActorRef


class IsolatedApplicationTests(SimpleTestCase):
    def test_only_owned_models_registered(self):
        self.assertEqual(
            {model._meta.app_label for model in apps.get_models()},
            {"integration_store"},
        )
        self.assertFalse(
            any(
                module in sys.modules
                for module in ("identity.models", "clients.models", "audit.models")
            )
        )

    def test_no_foreign_orm_relationships(self):
        for model in apps.get_models():
            for field in model._meta.fields:
                if field.is_relation:
                    self.assertEqual(
                        field.related_model._meta.app_label, "integration_store"
                    )

    def test_independent_migration_graph(self):
        graph = MigrationLoader(None).graph
        self.assertTrue(graph.nodes)
        self.assertEqual({app for app, name in graph.nodes}, {"integration_store"})

    def test_import_route_contract_matches_frozen_manifest(self):
        manifest = json.loads(
            (settings.BASE_DIR / "contracts/public-api-baseline.json").read_text()
        )
        expected = [
            route
            for route in manifest["routes"]
            if route["path"].startswith("/api/imports/")
        ]
        actual = []
        for pattern in get_resolver().url_patterns:
            if not str(pattern.pattern).startswith("api/imports/"):
                continue
            view = pattern.callback.view_class
            actual.append(
                {
                    "path": "/" + str(pattern.pattern),
                    "methods": sorted(
                        m.upper()
                        for m in view.http_method_names
                        if m not in ("head", "options") and hasattr(view, m)
                    ),
                }
            )
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 9)

    def test_no_unsigned_background_job_bypass(self):
        with self.assertRaises(PermissionDenied):
            RemoteAccess().authorize(ActorRef(pk=uuid4()), uuid4(), "imports.upload")

    def test_decision_cannot_change_actor_or_scope(self):
        actor = ActorRef(pk=uuid4())
        actor.credentials = {"synthetic": True}
        for decision in (
            {"actor_id": str(uuid4()), "grants": []},
            {"actor_id": str(actor.pk), "grants": [{"scope": "assigned"}]},
        ):
            with patch("integration_service.access.iam") as client:
                client.return_value.authorize.return_value = decision
                with self.assertRaises(PermissionDenied):
                    RemoteAccess().authorize(actor, uuid4())

    def test_every_authorization_includes_full_import_and_finance_capabilities(self):
        actor = ActorRef(pk=uuid4())
        actor.credentials = {"synthetic": True}
        with patch("integration_service.access.iam") as client:
            client.return_value.authorize.return_value = {
                "actor_id": str(actor.pk),
                "grants": [{"scope": "organization"}],
            }
            RemoteAccess().authorize(actor, uuid4(), "imports.approve")
            payload = client.return_value.authorize.call_args.args[0]
            self.assertEqual(
                set(payload["capabilities"]),
                {"imports.view", "clients.view_financial", "imports.approve"},
            )

    def test_slow_internal_response_has_a_total_io_deadline(self):
        import socket
        import threading
        import time
        from internal_api.client import InternalClient, ServiceUnavailable

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()

            def peer():
                try:
                    conn, _ = listener.accept()
                    with conn:
                        conn.recv(65536)
                        conn.sendall(b"HTTP/1.0 200 OK\r\nContent-Length: 100\r\n\r\n")
                        for _ in range(100):
                            conn.sendall(b" ")
                            time.sleep(0.03)
                except OSError:
                    pass

            worker = threading.Thread(target=peer, daemon=True)
            worker.start()
            started = time.monotonic()
            client = InternalClient(
                f"http://127.0.0.1:{listener.getsockname()[1]}",
                "synthetic",
                "synthetic" * 8,
                "iam",
                timeout=0.2,
            )
            with self.assertRaises(ServiceUnavailable):
                client.post("/internal/v1/principal/resolve", {})
            self.assertLess(time.monotonic() - started, 1.5)
            worker.join(timeout=2)
