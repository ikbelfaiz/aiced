from unittest.mock import patch
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.test import TestCase
from testing import fixtures
from identity.models import RoleAssignment
from clients.models import Party, Interaction, Opportunity, CRMProfile
from clients.workspace import create_party, edit_profile, save_activity
from audit.models import AuditEvent


class WorkspaceTests(TestCase):
    setUp = fixtures.SecurityFixtures.setUp
    login_as = fixtures.SecurityFixtures.login_as

    @classmethod
    def setUpTestData(cls):
        fixtures.SecurityFixtures.setUpTestData.__func__(cls)
        cls.workspace_role = fixtures.role(
            "workspace",
            [
                "clients.create",
                "clients.update_identity",
                "interactions.view",
                "interactions.manage",
                "opportunities.view",
                "opportunities.manage",
            ],
        )
        RoleAssignment.objects.create(
            membership=cls.manager_m, role=cls.workspace_role, scope="organization"
        )

    def test_workspace_scope_and_permissions(self):
        self.login_as(self.reader)
        data = self.client.get(f"/api/clients/{self.own.pk}/workspace/").json()
        self.assertFalse(data["permissions"]["view_accounts"])
        self.assertFalse(data["permissions"]["edit_identity"])
        self.assertEqual(data["provenance"]["synchronization"], "not_connected")
        for party in [self.same_org_hidden, self.other_org_hidden]:
            for tail in ["workspace/", "interactions/", "opportunities/"]:
                self.assertEqual(
                    self.client.get(f"/api/clients/{party.pk}/{tail}").status_code, 404
                )
        self.login_as(self.it)
        self.assertEqual(
            self.client.get(f"/api/clients/{self.own.pk}/workspace/").status_code, 404
        )

    def test_identity_ownership_strict_fields_and_create(self):
        self.login_as(self.manager)
        response = self.client.post(
            "/api/clients/create/",
            {
                "organization_id": str(self.org_a.pk),
                "kind": "physical",
                "first_name": "Synthetic",
                "last_name": "Manual",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        url = f"/api/clients/{pk}/identity/"
        self.assertEqual(
            self.client.patch(
                url,
                {"version": 1, "first_name": "Synthetic", "last_name": "Edited"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                url,
                {"version": 1, "first_name": "Stale", "last_name": "Edit"},
                format="json",
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.patch(
                url,
                {"version": 2, "first_name": "X", "last_name": "Y", "origin": "AICED"},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/clients/{self.own.pk}/identity/",
                {"version": 1, "first_name": "Forbidden", "last_name": "Source"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/clients/create/",
                {
                    "organization_id": str(self.org_b.pk),
                    "kind": "physical",
                    "first_name": "X",
                    "last_name": "Y",
                },
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/clients/create/",
                {
                    "organization_id": str(self.org_a.pk),
                    "kind": "physical",
                    "first_name": "X" * 100,
                    "last_name": "Y" * 100,
                },
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/clients/{self.own.pk}/accounts/",
                {"product_label": "Forbidden"},
                format="json",
            ).status_code,
            405,
        )

    def test_profile_field_validation_version_and_audit_rollback(self):
        self.login_as(self.reader)
        url = f"/api/clients/{self.own.pk}/profile/"
        self.assertEqual(
            self.client.patch(
                url, {"version": 1, "email": "bad"}, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(
                url, {"version": 1, "risk": "high"}, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(
                url,
                {
                    "version": 1,
                    "email": "synthetic@example.invalid",
                    "notes": "Synthetic note",
                },
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                url, {"version": 1, "notes": "lost update"}, format="json"
            ).status_code,
            409,
        )
        with patch(
            "clients.workspace.record", side_effect=RuntimeError("Synthetic failure")
        ):
            with self.assertRaises(RuntimeError):
                edit_profile(
                    self.reader, self.own.pk, {"version": 2, "notes": "Must roll back"}
                )
        self.assertEqual(CRMProfile.objects.get(party=self.own).notes, "Synthetic note")

    def test_activity_validation_scope_and_amount_precision(self):
        self.login_as(self.manager)
        url = f"/api/clients/{self.own.pk}/interactions/"
        payload = {
            "kind": "call",
            "subject": "Synthetic call",
            "occurred_at": (timezone.now() - timedelta(hours=1)).isoformat(),
            "notes": "Synthetic",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            self.client.patch(
                url + str(response.data["id"]) + "/",
                {"version": 1, "subject": "Edited"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/api/clients/{self.other_org_hidden.pk}/interactions/",
                payload,
                format="json",
            ).status_code,
            404,
        )
        payload["occurred_at"] = (timezone.now() + timedelta(days=1)).isoformat()
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 400)
        opp = f"/api/clients/{self.own.pk}/opportunities/"
        for amount in ["-1", "NaN", "1.1234"]:
            self.assertEqual(
                self.client.post(
                    opp,
                    {"title": "Synthetic opportunity", "amount": amount},
                    format="json",
                ).status_code,
                400,
            )
        result = self.client.post(
            opp, {"title": "Synthetic estimate", "amount": "60000.125"}, format="json"
        )
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data["amount"], "60000.125")
        self.login_as(self.reader)
        self.assertEqual(self.client.get(opp).status_code, 404)
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 404)
