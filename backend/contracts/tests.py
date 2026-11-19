"""Consumer contracts frozen before any route or persistence extraction."""

import hashlib
import json
from io import BytesIO
import openpyxl
from django.conf import settings
from django.test import TestCase
from django.urls import get_resolver
from identity.models import RoleAssignment
from ingestion.templates import TEMPLATES
from testing.fixtures import SecurityFixtures, role, PASSWORD
from contracts.additions import ADDITIONAL_ROUTES


class ConsumerContractChecks(SecurityFixtures):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        capabilities = [
            "clients.create",
            "clients.update_identity",
            "prospects.view",
            "prospects.manage",
            "interactions.view",
            "interactions.manage",
            "opportunities.view",
            "opportunities.manage",
            "imports.view",
            "imports.upload",
            "imports.policy_manage",
        ]
        RoleAssignment.objects.create(
            membership=cls.manager_m,
            role=role("contract-operator", capabilities),
            scope="organization",
        )
        RoleAssignment.objects.create(
            membership=cls.other_m,
            role=role(
                "contract-reviewer",
                ["imports.view", "imports.approve", "clients.view_financial"],
            ),
            scope="organization",
        )

    def page(self, response):
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(
            {"count", "next", "previous", "results"} <= response.data.keys()
        )
        self.assertIsInstance(response.data["count"], int)
        self.assertIsInstance(response.data["results"], list)
        return response.data["results"]

    def test_routes_and_historical_migrations_match_baseline(self):
        manifest = json.loads(
            (
                settings.BASE_DIR / "contracts/public-api-baseline.json"
            ).read_text(encoding="utf-8")
        )
        routes = []
        for pattern in get_resolver().url_patterns:
            view = pattern.callback.view_class
            methods = sorted(
                m.upper()
                for m in view.http_method_names
                if m not in ("head", "options") and hasattr(view, m)
            )
            routes.append({"path": "/" + str(pattern.pattern), "methods": methods})
        expected = manifest["routes"] + ADDITIONAL_ROUTES
        expected = [dict(route, methods=[method for method in route["methods"] if method != "POST"])
                    if route["path"] == "/api/imports/<uuid:organization_id>/policies/" else route
                    for route in expected]
        self.assertEqual(routes, expected)
        for filename, digest in manifest["historical_migrations"].items():
            self.assertEqual(
                hashlib.sha256((settings.BASE_DIR / filename).read_text(encoding='utf-8').encode('utf-8')).hexdigest(),
                digest,
                filename,
            )

    def test_authentication_cookie_csrf_and_grants_contract(self):
        response = self.client.get("/api/session/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(set(response.data), {"error"})
        self.login_as(self.manager)
        self.assertEqual(
            self.client.post(
                "/api/auth/login/",
                {"username": self.manager.username, "password": PASSWORD},
                format="json",
            ).status_code,
            200,
        )
        self.client.credentials(
            HTTP_X_CSRFTOKEN=self.client.get("/api/auth/csrf/").data["csrfToken"]
        )
        response = self.client.get("/api/session/")
        self.assertEqual(set(response.data), {"id", "username"})
        self.assertTrue(self.client.cookies["sessionid"]["httponly"])
        response = self.client.get("/api/auth/access/")
        self.assertEqual(set(response.data), {"assignments"})
        self.assertTrue(
            {
                "id",
                "organization_id",
                "organization_name",
                "scope",
                "expires_at",
                "permissions",
            }
            <= response.data["assignments"][0].keys()
        )
        self.assertEqual(set(self.client.get("/api/auth/csrf/").data), {"csrfToken"})
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 204)
        self.assertEqual(self.client.get("/api/session/").status_code, 403)

    def test_client_workspace_and_manual_entry_contract(self):
        self.login_as(self.manager)
        self.page(self.client.get("/api/clients/?page_size=1&kind=physical"))
        response = self.client.get("/api/clients/context/")
        self.assertEqual(str(response.data["organizations"][0]["id"]), str(self.org_a.pk))
        response = self.client.post(
            "/api/clients/create/",
            {
                "organization_id": str(self.org_a.pk),
                "kind": "legal",
                "legal_name": "SYNTHETIC contract company",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        root = f"/api/clients/{pk}/"
        self.assertEqual(self.client.get(root).status_code, 200)
        workspace = self.client.get(root + "workspace/").data
        self.assertTrue(
            {
                "is_prospect",
                "identity",
                "crm",
                "permissions",
                "provenance",
                "ownership",
                "relationship_manager",
                "version",
                "organization_id",
            }
            <= workspace.keys()
        )
        self.assertEqual(workspace["provenance"]["synchronization"], "not_connected")
        self.assertEqual(
            self.client.patch(
                root + "identity/",
                {"version": 1, "legal_name": "SYNTHETIC edited"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                root + "profile/",
                {"version": 1, "email": "contract@example.invalid"},
                format="json",
            ).data["version"],
            2,
        )
        self.assertEqual(
            self.client.patch(
                root + "profile/", {"version": 1, "notes": "stale"}, format="json"
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.patch(
                root + "crm/", {"notes": "SYNTHETIC legacy notes"}, format="json"
            ).status_code,
            200,
        )
        self.page(self.client.get(f"/api/clients/{self.own.pk}/accounts/"))

    def test_prospect_and_activity_contracts(self):
        self.login_as(self.manager)
        self.assertTrue(
            self.client.get("/api/prospects/context/").data["organizations"]
        )
        response = self.client.post(
            "/api/prospects/",
            {
                "organization_id": str(self.org_a.pk),
                "kind": "legal",
                "legal_name": "SYNTHETIC prospect",
                "qualification": {"source": "SYNTHETIC event"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        self.assertEqual(
            self.client.patch(
                f"/api/prospects/{pk}/",
                {"version": 1, "status": "qualified"},
                format="json",
            ).status_code,
            200,
        )
        for category, payload in [
            (
                "interactions",
                {
                    "kind": "call",
                    "subject": "SYNTHETIC call",
                    "occurred_at": "2026-01-01T10:00:00Z",
                },
            ),
            ("opportunities", {"title": "SYNTHETIC estimate", "amount": "123.456"}),
        ]:
            root = f"/api/clients/{pk}/{category}/"
            response = self.client.post(root, payload, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            if category == "opportunities":
                self.assertEqual(response.data["amount"], "123.456")
            url = root + str(response.data["id"]) + "/"
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(
                self.client.patch(
                    url, {"version": 1, "notes": "SYNTHETIC edit"}, format="json"
                ).data["version"],
                2,
            )
            self.page(self.client.get(root))
        row = self.page(self.client.get("/api/prospects/?search=SYNTHETIC"))[0]
        self.assertTrue(
            {
                "id",
                "display_name",
                "status",
                "version",
                "can_edit",
                "last_interaction",
                "relationship_manager",
            }
            <= row.keys()
        )
        self.assertEqual(self.client.get(f"/api/prospects/{pk}/").status_code, 200)

    def test_import_upload_preview_publication_download_and_replay_contract(self):
        self.login_as(self.manager)
        self.assertEqual(
            self.client.get("/api/imports/context/").data["mode"],
            "immutable_snapshots_only",
        )
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = "Tier"
        sheet.append(TEMPLATES["legal"]["headers"])
        for key in ["SYNTH-VALID", "SYNTH-DUP", "SYNTH-DUP"]:
            row = [None] * 25
            row[1] = key
            row[3] = "SYNTHETIC company"
            sheet.append(row)
        out = BytesIO()
        book.save(out)
        content = out.getvalue()
        root = f"/api/imports/{self.org_a.pk}/"
        upload = (
            root
            + "upload/?source_as_of=2026-01-01&date_format=ISO&snapshot_kind=partial&data_scope=synthetic"
        )
        response = self.client.post(
            upload, content, content_type="application/octet-stream"
        )
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        replay = self.client.post(
            upload, content, content_type="application/octet-stream"
        )
        self.assertEqual((replay.status_code, replay.data["id"]), (200, pk))
        url = root + f"batches/{pk}/"
        preview = self.client.get(url)
        self.assertEqual(len(self.page(preview)), 3)
        self.assertTrue({"batch", "headers", "history"} <= preview.data.keys())
        self.assertEqual(preview.data["batch"]["rejected"], 2)
        self.page(self.client.get(root + "batches/"))
        csv = self.client.get(url + "rejections/")
        self.assertEqual(csv.status_code, 200)
        self.assertTrue(csv["Content-Type"].startswith("text/csv"))
        self.assertIn("attachment", csv["Content-Disposition"])
        policy = self.client.post(
            root + "policies/",
            {
                "template": "legal",
                "key_column": 2,
                "rationale": "SYNTHETIC explicit contract policy",
            },
            format="json",
        )
        self.assertEqual(policy.status_code, 405)
        self.assertIsInstance(self.client.get(root + "policies/").data, list)
        self.assertEqual(self.client.post(url + "publish/", {"skip_rejected": True}, format="json").status_code, 403)
        self.login_as(self.other)
        self.assertEqual(
            self.client.post(
                url + "publish/",
                {"skip_rejected": True},
                format="json",
            ).data["published_rows"],
            1,
        )

    def test_denial_fields_and_counts_cannot_be_widened_by_consumers(self):
        self.login_as(self.reader)
        self.assertEqual(
            self.client.get("/api/clients/?search=Synthetic hidden").data["count"], 0
        )
        for pk in [self.same_org_hidden.pk, self.other_org_hidden.pk]:
            self.assertEqual(
                self.client.get(f"/api/clients/{pk}/workspace/").status_code, 404
            )
        self.assertEqual(
            self.client.get(f"/api/clients/{self.own.pk}/accounts/").status_code, 403
        )
        self.assertEqual(
            self.client.patch(
                f"/api/clients/{self.own.pk}/profile/",
                {"version": 1, "origin": "AICED"},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/prospects/",
                {"organization_id": str(self.org_a.pk)},
                format="json",
            ).status_code,
            403,
        )
        self.login_as(self.it)
        self.assertEqual(self.client.get("/api/clients/").status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/api/organizations/{self.org_a.pk}/role-assignments/",
                {
                    "membership_id": str(self.it_m.pk),
                    "role_id": str(self.manager_role.pk),
                    "scope": "organization",
                },
                format="json",
            ).status_code,
            403,
        )


class ConsumerContracts(ConsumerContractChecks, TestCase):
    """The same contract checks also run over real HTTP in gateway_tests."""
