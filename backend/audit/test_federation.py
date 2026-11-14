from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from testing.fixtures import SecurityFixtures
from ingestion.models import RuntimeState
from audit.services import record
from internal_api.client import ServiceUnavailable


@override_settings(
    INTEGRATION_AUDIT_URL="http://127.0.0.1:8002",
    INTEGRATION_AUDIT_KEY_ID="iam-audit",
    AICED_INTERNAL_KEYS={
        "iam-audit": {
            "secret": "synthetic-federation-key-" + "x" * 40,
            "service": "iam",
            "audiences": ["integration"],
        }
    },
)
class FederatedAuditTests(SecurityFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.manager)
        RuntimeState.objects.update_or_create(pk=1, defaults={"mode": "service"})
        self.local = record(
            "clients.synthetic", actor=self.manager, organization_id=self.org_a.pk
        )
        self.remote = {
            "id": str(uuid4()),
            "occurred_at": (timezone.now() + timedelta(seconds=1)).isoformat(),
            "actor_id": str(self.reader.pk),
            "organization_id": str(self.org_a.pk),
            "action": "imports.staged",
            "target_id": str(uuid4()),
            "result": "success",
            "request_id": str(uuid4()),
            "context": {"rows": 1},
        }

    def test_scoped_combined_order_attribution_and_duplicate_history_exclusion(self):
        # Copied historical source imports must be shown once, from the canonical service.
        record("imports.staged", actor=self.reader, organization_id=self.org_a.pk)
        with patch("audit.federation.InternalClient") as client:
            client.return_value.post.return_value = {
                "count": 1,
                "results": [self.remote],
            }
            response = self.client.get("/api/audit/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(str(response.data["results"][0]["id"]), self.remote["id"])
        self.assertEqual(
            str(response.data["results"][0]["actor_id"]), str(self.reader.pk)
        )
        self.assertEqual(str(response.data["results"][1]["id"]), str(self.local.pk))

    def test_failure_or_foreign_organization_never_returns_a_partial_listing(self):
        for result in [
            ServiceUnavailable(),
            {
                "count": 1,
                "results": [{**self.remote, "organization_id": str(self.org_b.pk)}],
            },
            {
                "count": 1,
                "results": [{**self.remote, "occurred_at": "2026-01-01T10:00:00"}],
            },
        ]:
            with patch("audit.federation.InternalClient") as client:
                if isinstance(result, Exception):
                    client.return_value.post.side_effect = result
                else:
                    client.return_value.post.return_value = result
                response = self.client.get("/api/audit/")
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("results", response.data)

    def test_no_audit_grant_denied_before_remote_communication(self):
        self.client.force_login(self.it)
        with patch("audit.federation.InternalClient") as client:
            self.assertEqual(self.client.get("/api/audit/").status_code, 403)
            client.assert_not_called()

    def test_frozen_copy_never_returns_stale_canonical_history(self):
        RuntimeState.objects.filter(pk=1).update(mode="frozen")
        with patch("audit.federation.InternalClient") as client:
            self.assertEqual(self.client.get("/api/audit/").status_code, 503)
            client.assert_not_called()

    def test_last_invalid_and_missing_page_contracts(self):
        with patch("audit.federation.InternalClient") as client:
            client.return_value.post.return_value = {
                "count": 1,
                "results": [self.remote],
            }
            self.assertEqual(self.client.get("/api/audit/?page=last").status_code, 200)
            self.assertEqual(self.client.get("/api/audit/?page=0").status_code, 404)
            self.assertEqual(self.client.get("/api/audit/?page=9999").status_code, 404)

    def test_merge_pagination_remains_stable_across_remote_chunks(self):
        records = [
            {
                **self.remote,
                "id": str(uuid4()),
                "occurred_at": (
                    timezone.now() + timedelta(seconds=300 - i)
                ).isoformat(),
            }
            for i in range(205)
        ]

        visible = list(records)

        def fetch(path, payload):
            start = 0
            if "before_id" in payload:
                # A concurrently committed event above the cursor must not
                # shift offsets or duplicate the last row of the prior chunk.
                if len(visible) == 205:
                    visible.insert(
                        0,
                        {
                            **self.remote,
                            "id": str(uuid4()),
                            "occurred_at": (
                                timezone.now() + timedelta(seconds=500)
                            ).isoformat(),
                        },
                    )
                start = (
                    next(
                        i
                        for i, row in enumerate(visible)
                        if row["id"] == payload["before_id"]
                    )
                    + 1
                )
            return {"count": len(visible), "results": visible[start : start + 100]}

        with patch("audit.federation.InternalClient") as client:
            client.return_value.post.side_effect = fetch
            response = self.client.get("/api/audit/?page=5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 206)
        self.assertEqual(len(response.data["results"]), 6)
        self.assertEqual(str(response.data["results"][0]["id"]), records[200]["id"])
        self.assertEqual(str(response.data["results"][-1]["id"]), str(self.local.pk))
