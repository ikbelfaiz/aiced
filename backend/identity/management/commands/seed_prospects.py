"""Explicit opt-in synthetic capability grant; no production role changes."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from identity.models import Capability, Role, RoleAssignment, Membership
from clients.models import Prospect
from clients.prospects import create_prospect
from audit.services import record


class Command(BaseCommand):
    help = "Prepare synthetic prospects for the existing synthetic workspace operator."

    def add_arguments(self, parser):
        parser.add_argument("--confirm-synthetic", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or not options["confirm_synthetic"]:
            raise CommandError("DEBUG et confirmation synthétique requis.")
        member = Membership.objects.select_related("user", "organization").get(
            user__username="synthetic.operator.a",
            organization__code="SYNTHETIC-A",
            is_active=True,
        )
        role, created = Role.objects.get_or_create(
            code="synthetic-prospects", defaults={"name": "DÉMONSTRATION prospects"}
        )
        for code in ["prospects.view", "prospects.manage"]:
            Capability.objects.get_or_create(code=code, defaults={"description": code})
        if created:
            role.permissions.set(["prospects.view", "prospects.manage"])
        grant, created = RoleAssignment.objects.get_or_create(
            membership=member, role=role, scope="organization"
        )
        if created:
            record(
                "seed.prospects_granted",
                organization_id=member.organization_id,
                target_id=grant.pk,
            )
        for label, source, status in [
            ("Contact Alpha", "Événement synthétique", "contact"),
            ("Entreprise Bêta", "Recommandation synthétique", "qualified"),
        ]:
            name = f"SYNTHÉTIQUE {label}"
            if not Prospect.objects.filter(
                party__organization=member.organization, party__display_name=name
            ).exists():
                prospect = create_prospect(
                    member.user,
                    {
                        "organization_id": str(member.organization_id),
                        "kind": "legal",
                        "legal_name": name,
                        "qualification": {"source": source, "status": status},
                    },
                )
                prospect.party.assigned_to = member
                prospect.party.save(update_fields=["assigned_to"])
        self.stdout.write(
            "Prospects synthétiques préparés ; aucun compte ou identifiant source modifié."
        )
