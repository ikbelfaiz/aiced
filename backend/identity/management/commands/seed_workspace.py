"""Separate synthetic roles, never expand the existing Phase 1 roles silently."""

import os
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from audit.services import record
from identity.models import (
    Capability,
    Role,
    User,
    Membership,
    RoleAssignment,
    Organization,
)


class Command(BaseCommand):
    help = "Create synthetic workspace operator and separate reviewer in organization A only."

    def add_arguments(self, parser):
        parser.add_argument("--confirm-synthetic", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["confirm_synthetic"] or (
            not settings.DEBUG and os.environ.get("AICED_SYNTHETIC_DEMO") != "1"
        ):
            raise CommandError("Mode démo synthétique explicite et confirmation synthétique requis.")
        password = os.environ.get("AICED_SEED_PASSWORD", "")
        validate_password(password)
        org = Organization.objects.get(code="SYNTHETIC-A")
        common = ["clients.view", "clients.view_financial", "imports.view"]
        roles = {
            "operator": common
            + [
                "clients.create",
                "clients.update_identity",
                "clients.update_crm",
                "interactions.view",
                "interactions.manage",
                "opportunities.view",
                "opportunities.manage",
                "imports.upload",
                "imports.policy_manage",
            ],
            "reviewer": common + ["imports.approve"],
        }
        for label, codes in roles.items():
            for code in codes:
                Capability.objects.get_or_create(
                    code=code, defaults={"description": code}
                )
            role, created = Role.objects.get_or_create(
                code=f"synthetic-workspace-{label}",
                defaults={"name": f"DÉMONSTRATION workspace {label}"},
            )
            if created:
                role.permissions.set(codes)
            user, created = User.objects.get_or_create(username=f"synthetic.{label}.a")
            if created:
                user.set_password(password)
                user.save()
            member, _ = Membership.objects.get_or_create(user=user, organization=org)
            grant, created = RoleAssignment.objects.get_or_create(
                membership=member, role=role, scope="organization"
            )
            if created:
                record(
                    "seed.workspace_granted", target_id=grant.pk, organization_id=org.pk
                )
        self.stdout.write(
            "Comptes synthétiques operator/reviewer préparés ; aucun rôle existant élargi."
        )
