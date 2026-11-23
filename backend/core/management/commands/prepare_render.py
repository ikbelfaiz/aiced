"""Initialize the single-service Render deployment before starting HTTP workers."""
import os

import psycopg
from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction


class Command(BaseCommand):
    help = 'Apply migrations and bootstrap an explicitly synthetic empty Render database.'

    def handle(self, *args, **options):
        if not os.environ.get('DATABASE_URL'):
            raise CommandError('DATABASE_URL est absente. Reliez le service à sa base PostgreSQL dans Render > Environment.')
        if getattr(settings, 'IAM_OWNED', False) or getattr(settings, 'IAM_REMOTE', False):
            raise CommandError('Cette commande est réservée au déploiement Render à base unique.')
        db = settings.DATABASES['default']
        try:
            with psycopg.connect(host=db['HOST'], port=db['PORT'], dbname=db['NAME'],
                                 user=db['USER'], password=db['PASSWORD'],
                                 connect_timeout=15, autocommit=True,
                                 options='-c lock_timeout=60000') as lock:
                # A session lock on a separate connection survives migration commits.
                lock.execute('SELECT pg_advisory_lock(%s)', [4711239301896722])
                try:
                    call_command('migrate', interactive=False, stdout=self.stdout)
                    self.bootstrap_demo()
                finally:
                    lock.execute('SELECT pg_advisory_unlock(%s)', [4711239301896722])
        except psycopg.Error as exc:
            # Do not put connection strings, usernames or passwords in startup logs.
            code = exc.sqlstate or 'connection_error'
            raise CommandError(f'PostgreSQL indisponible (code {code}). Vérifiez DATABASE_URL et l’état de la base Render.') from None
        self.stdout.write(self.style.SUCCESS('Base prête ; démarrage du serveur autorisé.'))

    def bootstrap_demo(self):
        if os.environ.get('AICED_SYNTHETIC_DEMO') != '1':
            return
        from identity.models import Organization, User
        from clients.models import Party
        with transaction.atomic():
            # Never reseed an existing installation or silently extend its grants.
            if User.objects.exists() or Organization.objects.exists() or Party.objects.exists():
                self.stdout.write('Base existante conservée ; aucune donnée de démonstration ajoutée.')
                return
            call_command('seed_synthetic', confirm_synthetic=True, stdout=self.stdout)
            call_command('seed_workspace', confirm_synthetic=True, stdout=self.stdout)
