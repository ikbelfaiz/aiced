import os
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from audit.services import record
from clients.models import Party, PhysicalPerson, CRMProfile, FinancialAccount
from identity.models import Capability, Organization, Role, Membership, RoleAssignment, User

CAPABILITIES = [
    'clients.view', 'clients.create', 'clients.update_crm', 'clients.view_financial',
    'opportunities.manage', 'imports.upload', 'imports.approve',
    'reconciliation.view', 'reconciliation.resolve', 'users.manage', 'reports.view_global', 'audit.view',
]


class Command(BaseCommand):
    help = 'Seed explicitly synthetic development data; refuses non-debug environments.'

    def add_arguments(self, parser):
        parser.add_argument('--confirm-synthetic', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or not options['confirm_synthetic']:
            raise CommandError('DEBUG=1 et --confirm-synthetic sont requis.')
        password = os.environ.get('AICED_SEED_PASSWORD', '')
        try:
            validate_password(password)
        except ValidationError:
            raise CommandError('Définir AICED_SEED_PASSWORD avec un mot de passe conforme (non journalisé).')
        for code in CAPABILITIES:
            Capability.objects.get_or_create(code=code, defaults={'description': code})
        role_codes = {
            'synthetic-reader': ['clients.view', 'clients.update_crm'],
            'synthetic-manager': ['clients.view', 'clients.update_crm', 'clients.view_financial', 'users.manage', 'audit.view'],
            'synthetic-it': ['users.manage'],
        }
        roles = {}
        for code, capabilities in role_codes.items():
            role, created = Role.objects.get_or_create(code=code, defaults={'name': f'DÉMONSTRATION — {code}'})
            if created:
                role.permissions.set(capabilities)
                record('seed.role_created', target_id=role.pk)
            roles[code] = role
        for suffix in ['a', 'b']:
            org, _ = Organization.objects.get_or_create(code=f'SYNTHETIC-{suffix.upper()}', defaults={'name': f'Organisation synthétique {suffix.upper()}'})
            for prefix, role_code, scope in [('reader', 'synthetic-reader', 'assigned'),
                                              ('manager', 'synthetic-manager', 'organization'),
                                              ('it', 'synthetic-it', 'organization')]:
                username = f'synthetic.{prefix}.{suffix}'
                user, created = User.objects.get_or_create(username=username)
                if created:
                    user.set_password(password)
                    user.save(update_fields=['password'])
                member, _ = Membership.objects.get_or_create(user=user, organization=org)
                assignment, created = RoleAssignment.objects.get_or_create(membership=member, role=roles[role_code], scope=scope)
                if created:
                    record('seed.permissions_granted', organization_id=org.pk, target_id=assignment.pk)
                if prefix == 'reader':
                    party, _ = Party.objects.get_or_create(organization=org, display_name=f'CLIENT SYNTHÉTIQUE {suffix.upper()}',
                                                          defaults={'kind': 'physical', 'assigned_to': member})
                    PhysicalPerson.objects.get_or_create(party=party, defaults={'first_name': 'Synthétique', 'last_name': suffix.upper()})
                    CRMProfile.objects.get_or_create(party=party)
                    FinancialAccount.objects.get_or_create(source='SYNTHETIC_ONLY', external_id=f'DEMO-ACCOUNT-{suffix}',
                        defaults={'party': party, 'source_as_of': timezone.now(), 'product_label': 'Compte de démonstration sans encours'})
        record('seed.completed')
        self.stdout.write(self.style.SUCCESS('Données SYNTHÉTIQUES préparées. Comptes synthetic.{reader,manager,it}.{a,b}. Aucun mot de passe existant remplacé.'))
