"""S6 preparation regressions; all rows are synthetic and test-DB-only."""

from unittest.mock import patch
from django.test import TestCase
from django.http import Http404
from rest_framework.exceptions import ValidationError
from audit.models import AuditEvent, AuditOutbox
from clients.models import Opportunity
from clients.workspace import save_activity
from commercial.contracts import OpportunityInput
from commercial.services import save_opportunity
from identity.models import RoleAssignment
from testing.fixtures import SecurityFixtures, role


class CommercialBoundaryTests(SecurityFixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        commercial = role(
            "synthetic-commercial", ["opportunities.view", "opportunities.manage"]
        )
        RoleAssignment.objects.create(
            membership=cls.reader_m, role=commercial, scope="assigned"
        )

    def test_local_dispatch_preserves_decimal_version_and_audit(self):
        item = save_activity(
            self.reader,
            self.own.pk,
            "opportunities",
            {"title": "Synthetic", "amount": "123.456"},
        )
        self.assertEqual(str(item.amount), "123.456")
        event = AuditEvent.objects.get(
            target_id=item.pk, action="clients.opportunities_saved"
        )
        self.assertTrue(AuditOutbox.objects.filter(event=event).exists())
        updated = save_opportunity(
            self.reader, self.own.pk, {"version": 1, "status": "won"}, item.pk
        )
        self.assertEqual(updated.version, 2)
        self.assertEqual(updated.status, "won")

    def test_cross_client_and_cross_organization_denied(self):
        for party in (self.same_org_hidden, self.other_org_hidden):
            with self.assertRaises(Http404):
                save_opportunity(self.reader, party.pk, {"title": "Synthetic"})
        self.assertFalse(Opportunity.objects.exists())

    def test_required_audit_failure_rolls_back_opportunity(self):
        with patch(
            "commercial.services.record",
            side_effect=RuntimeError("synthetic audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                save_opportunity(self.reader, self.own.pk, {"title": "Synthetic"})
        self.assertFalse(Opportunity.objects.exists())

    def test_author_and_party_cannot_be_injected(self):
        for field in ("author_id", "party_id", "organization_id"):
            data = OpportunityInput(
                data={"title": "Synthetic", field: str(self.other.pk)}
            )
            self.assertFalse(data.is_valid(), field)
        self.assertFalse(
            OpportunityInput(data={"title": "Synthetic", "amount": "-1"}).is_valid()
        )

    def test_unknown_activity_does_not_create_opportunity(self):
        with self.assertRaises(ValidationError):
            save_activity(self.reader, self.own.pk, "arbitrary", {"title": "Synthetic"})
        self.assertFalse(Opportunity.objects.exists())

    def test_update_audit_failure_preserves_old_value_and_version(self):
        item = save_opportunity(self.reader, self.own.pk, {"title": "Synthetic"})
        with patch(
            "commercial.services.record",
            side_effect=RuntimeError("synthetic audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                save_opportunity(
                    self.reader,
                    self.own.pk,
                    {"version": 1, "title": "Changed"},
                    item.pk,
                )
        item.refresh_from_db()
        self.assertEqual(item.title, "Synthetic")
        self.assertEqual(item.version, 1)

    def test_stale_version_does_not_overwrite(self):
        from clients.workspace import Conflict

        item = save_opportunity(self.reader, self.own.pk, {"title": "Synthetic"})
        with self.assertRaises(Conflict):
            save_opportunity(
                self.reader, self.own.pk, {"version": 99, "title": "Changed"}, item.pk
            )
        item.refresh_from_db()
        self.assertEqual(item.title, "Synthetic")
        self.assertEqual(item.version, 1)
