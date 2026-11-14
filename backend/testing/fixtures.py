"""Shared synthetic fixtures; no TestCase class is imported across domain suites."""

import uuid
from django.utils import timezone
from rest_framework.test import APIClient
from clients.models import Party, PhysicalPerson, CRMProfile, FinancialAccount
from identity.models import (
    User,
    Organization,
    Membership,
    Capability,
    Role,
    RoleAssignment,
)

PASSWORD = "Synthetic-test-passphrase-8675309!"


def role(code, permissions):
    result = Role.objects.create(code=code, name=code)
    for permission in permissions:
        capability, _ = Capability.objects.get_or_create(
            code=permission, defaults={"description": permission}
        )
        result.permissions.add(capability)
    return result


def party(organization, member, label):
    result = Party.objects.create(
        organization=organization,
        assigned_to=member,
        kind="physical",
        display_name=label,
    )
    PhysicalPerson.objects.create(party=result, first_name="Synthetic", last_name=label)
    CRMProfile.objects.create(party=result)
    FinancialAccount.objects.create(
        party=result,
        source="SYNTHETIC_ONLY",
        external_id=str(uuid.uuid4()),
        source_as_of=timezone.now(),
        product_label="Synthetic account",
    )
    return result


class SecurityFixtures:
    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(code="SYNTHETIC-A", name="Synthetic A")
        cls.org_b = Organization.objects.create(
            code="SYNTHETIC-B", name="Synthetic B", parent=cls.org_a
        )
        cls.reader_role = role(
            "synthetic-reader", ["clients.view", "clients.update_crm"]
        )
        cls.finance_role = role("synthetic-finance", ["clients.view_financial"])
        cls.it_role = role("synthetic-it", ["users.manage"])
        cls.manager_role = role(
            "synthetic-manager",
            [
                "users.manage",
                "clients.view",
                "clients.update_crm",
                "clients.view_financial",
                "audit.view",
            ],
        )
        cls.reader = User.objects.create_user("synthetic.reader", password=PASSWORD)
        cls.other = User.objects.create_user("synthetic.other", password=PASSWORD)
        cls.it = User.objects.create_user(
            "synthetic.it", password=PASSWORD, is_staff=True, is_superuser=True
        )
        cls.manager = User.objects.create_user("synthetic.manager", password=PASSWORD)
        cls.reader_m = Membership.objects.create(
            user=cls.reader, organization=cls.org_a
        )
        cls.other_m = Membership.objects.create(user=cls.other, organization=cls.org_a)
        cls.it_m = Membership.objects.create(user=cls.it, organization=cls.org_a)
        cls.manager_m = Membership.objects.create(
            user=cls.manager, organization=cls.org_a
        )
        cls.other_b = Membership.objects.create(user=cls.other, organization=cls.org_b)
        cls.reader_grant = RoleAssignment.objects.create(
            membership=cls.reader_m, role=cls.reader_role, scope="assigned"
        )
        RoleAssignment.objects.create(
            membership=cls.other_m, role=cls.reader_role, scope="assigned"
        )
        RoleAssignment.objects.create(
            membership=cls.it_m, role=cls.it_role, scope="organization"
        )
        RoleAssignment.objects.create(
            membership=cls.manager_m, role=cls.manager_role, scope="organization"
        )
        cls.own = party(cls.org_a, cls.reader_m, "Synthetic owned")
        cls.same_org_hidden = party(cls.org_a, cls.other_m, "Synthetic hidden A")
        cls.other_org_hidden = party(cls.org_b, cls.other_b, "Synthetic hidden B")

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def login_as(self, user):
        self.client.force_login(user)
        response = self.client.get("/api/auth/csrf/")
        self.client.credentials(HTTP_X_CSRFTOKEN=response.json()["csrfToken"])

    def assignment_url(self, org=None):
        return f"/api/organizations/{(org or self.org_a).pk}/role-assignments/"

    def grant(self, member=None, role_obj=None, scope="assigned", **extra):
        return self.client.post(
            self.assignment_url(),
            {
                "membership_id": str((member or self.other_m).pk),
                "role_id": str((role_obj or self.reader_role).pk),
                "scope": scope,
                **extra,
            },
            format="json",
        )
