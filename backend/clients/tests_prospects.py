from unittest.mock import patch
from django.test import TestCase
from testing import fixtures
from identity.models import RoleAssignment
from clients.models import Prospect, Party, FinancialAccount, LegalEntity
from clients.prospects import create_prospect
from audit.models import AuditEvent


class ProspectTests(TestCase):
    setUp = fixtures.SecurityFixtures.setUp
    login_as = fixtures.SecurityFixtures.login_as

    @classmethod
    def setUpTestData(cls):
        fixtures.SecurityFixtures.setUpTestData.__func__(cls)
        cls.prospect_role = fixtures.role(
            "prospect-synthetic",
            [
                "prospects.view",
                "prospects.manage",
                "clients.create",
                "interactions.view",
                "interactions.manage",
                "opportunities.view",
                "opportunities.manage",
            ],
        )
        RoleAssignment.objects.create(
            membership=cls.manager_m, role=cls.prospect_role, scope="organization"
        )

    def payload(self, org=None):
        return {
            "organization_id": str((org or self.org_a).pk),
            "kind": "physical",
            "first_name": "Synthetic",
            "last_name": "Prospect",
            "qualification": {"source": "Synthetic event", "status": "contact"},
        }

    def create(self):
        self.login_as(self.manager)
        response = self.client.post("/api/prospects/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["id"]

    def test_vertical_slice_and_separation(self):
        accounts = FinancialAccount.objects.count()
        pk = self.create()
        self.assertEqual(Party.objects.get(pk=pk).origin, "AICED")
        self.assertNotIn(
            pk,
            [
                str(row["id"])
                for row in self.client.get("/api/clients/").data["results"]
            ],
        )
        self.assertEqual(self.client.get("/api/prospects/").data["count"], 1)
        self.assertTrue(
            self.client.get(f"/api/clients/{pk}/workspace/").data["is_prospect"]
        )
        response = self.client.post(
            f"/api/clients/{pk}/interactions/",
            {
                "kind": "call",
                "subject": "Synthetic call",
                "occurred_at": "2026-01-01T10:00:00Z",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNotNone(
            self.client.get(f"/api/prospects/{pk}/").data["last_interaction"]
        )
        response = self.client.post(
            f"/api/clients/{pk}/opportunities/",
            {"title": "Synthetic estimate", "amount": "123.456"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["amount"], "123.456")
        self.assertEqual(FinancialAccount.objects.count(), accounts)
        self.assertTrue(
            AuditEvent.objects.filter(action="prospects.created", target_id=pk).exists()
        )

    def test_validation_version_and_no_source_link(self):
        pk = self.create()
        url = f"/api/prospects/{pk}/"
        for data in [
            {"version": 1, "status": "converted"},
            {"version": 1, "party_id": str(self.own.pk)},
            {"version": 1, "source": "X" * 121},
            {"version": 1, "next_action_date": "2026-11-20"},
        ]:
            self.assertEqual(
                self.client.patch(url, data, format="json").status_code, 400
            )
        self.assertEqual(
            self.client.patch(
                url,
                {
                    "version": 1,
                    "status": "qualified",
                    "next_action": "Synthetic meeting",
                    "next_action_date": "2026-11-20",
                },
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                url, {"version": 1, "status": "closed"}, format="json"
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.patch(
                url, {"version": 2, "next_action": ""}, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get("/api/prospects/?status=invalid").status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/prospects/?status=qualified").data["count"], 1
        )
        self.assertEqual(
            self.client.patch(
                f"/api/prospects/{self.own.pk}/",
                {"version": 1, "status": "qualified"},
                format="json",
            ).status_code,
            404,
        )

    def test_all_access_paths_deny_hidden_prospect_and_privilege_escalation(self):
        pk = self.create()
        for actor in [self.reader, self.it]:
            self.login_as(actor)
            self.assertEqual(
                self.client.post(
                    "/api/prospects/", self.payload(), format="json"
                ).status_code,
                403,
            )
            self.assertEqual(self.client.get("/api/prospects/").status_code, 403)
            for path in [
                f"/api/prospects/{pk}/",
                f"/api/clients/{pk}/",
                f"/api/clients/{pk}/workspace/",
                f"/api/clients/{pk}/interactions/",
                f"/api/clients/{pk}/opportunities/",
            ]:
                expected = (
                    403 if actor == self.it and path == f"/api/clients/{pk}/" else 404
                )
                self.assertEqual(self.client.get(path).status_code, expected, path)
            self.assertEqual(
                self.client.patch(
                    f"/api/clients/{pk}/crm/", {"notes": "Forbidden"}, format="json"
                ).status_code,
                403 if actor == self.it else 404,
            )
        self.login_as(self.manager)
        self.assertEqual(
            self.client.post(
                "/api/prospects/", self.payload(self.org_b), format="json"
            ).status_code,
            403,
        )

    def test_assigned_scope_intersection_and_revocation(self):
        pk = self.create()
        party = Party.objects.get(pk=pk)
        party.assigned_to = self.reader_m
        party.save()
        # Organization-wide client visibility cannot widen assigned-only prospects.
        RoleAssignment.objects.filter(
            membership=self.manager_m, role=self.prospect_role
        ).update(scope="assigned")
        self.assertEqual(self.client.get(f"/api/prospects/{pk}/").status_code, 404)
        party.assigned_to = self.manager_m
        party.save()
        self.assertEqual(self.client.get(f"/api/prospects/{pk}/").status_code, 200)
        RoleAssignment.objects.filter(
            membership=self.manager_m, role=self.prospect_role
        ).update(is_active=False)
        self.assertEqual(
            self.client.patch(
                f"/api/prospects/{pk}/",
                {"version": 1, "status": "qualified"},
                format="json",
            ).status_code,
            404,
        )

    def test_atomic_rollback_and_no_unauthorized_creation(self):
        before = Party.objects.count()
        with patch(
            "clients.prospects.record",
            side_effect=RuntimeError("Synthetic audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                create_prospect(self.manager, self.payload())
        self.assertEqual(Party.objects.count(), before)

        self.login_as(self.manager)
        payload = self.payload()
        payload["qualification"]["next_action_date"] = "2026-11-20"
        self.assertEqual(
            self.client.post("/api/prospects/", payload, format="json").status_code, 400
        )
        self.assertEqual(Party.objects.count(), before)

    def test_cross_organization_reads_writes_counts_and_csrf(self):
        pk = self.create()
        hidden = Party.objects.create(
            organization=self.org_b,
            kind="legal",
            origin="AICED",
            display_name="SYNTHETIC Hidden",
        )
        LegalEntity.objects.create(party=hidden, legal_name=hidden.display_name)
        Prospect.objects.create(party=hidden)
        self.assertEqual(self.client.get("/api/prospects/").data["count"], 1)
        self.assertEqual(
            self.client.get("/api/prospects/?search=Hidden").data["count"], 0
        )
        self.assertEqual(
            self.client.get(f"/api/prospects/{hidden.pk}/").status_code, 404
        )
        self.assertEqual(
            self.client.patch(
                f"/api/prospects/{hidden.pk}/",
                {"version": 1, "status": "qualified"},
                format="json",
            ).status_code,
            404,
        )
        self.client.credentials()
        self.assertEqual(
            self.client.patch(
                f"/api/prospects/{pk}/",
                {"version": 1, "status": "qualified"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/prospects/", self.payload(), format="json"
            ).status_code,
            403,
        )
