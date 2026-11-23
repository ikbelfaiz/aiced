import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TestCase

from core.management.commands.prepare_render import Command


class RenderStartupTests(SimpleTestCase):
    def test_missing_database_url_fails_before_migration(self):
        with patch.dict(os.environ, {'DATABASE_URL': ''}), patch('core.management.commands.prepare_render.call_command') as run:
            with self.assertRaisesMessage(CommandError, 'DATABASE_URL est absente'):
                call_command('prepare_render', stdout=StringIO())
            run.assert_not_called()

    def test_migration_failure_unlocks_and_does_not_seed(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://unused.invalid/db'}), patch('core.management.commands.prepare_render.psycopg.connect') as connect, patch('core.management.commands.prepare_render.call_command', side_effect=CommandError('migration failed')), patch.object(Command, 'bootstrap_demo') as seed:
            with self.assertRaisesMessage(CommandError, 'migration failed'):
                call_command('prepare_render', stdout=StringIO())
            connection = connect.return_value.__enter__.return_value
            self.assertIn('pg_advisory_unlock', connection.execute.call_args_list[-1].args[0])
            seed.assert_not_called()


class RenderBootstrapTests(TestCase):
    def test_bootstrap_requires_explicit_synthetic_mode(self):
        with patch.dict(os.environ, {'AICED_SYNTHETIC_DEMO': '0'}), patch('core.management.commands.prepare_render.call_command') as seed:
            Command(stdout=StringIO()).bootstrap_demo()
            seed.assert_not_called()

    def test_existing_accounts_are_not_reseeded(self):
        from identity.models import User
        User.objects.create_user('synthetic.existing', password='Synthetic-Test-Only-5468!')
        with patch.dict(os.environ, {'AICED_SYNTHETIC_DEMO': '1'}), patch('core.management.commands.prepare_render.call_command') as seed:
            Command(stdout=StringIO()).bootstrap_demo()
            seed.assert_not_called()

    def test_fresh_demo_runs_both_seeds(self):
        with patch.dict(os.environ, {'AICED_SYNTHETIC_DEMO': '1'}), patch('core.management.commands.prepare_render.call_command') as seed:
            Command(stdout=StringIO()).bootstrap_demo()
            self.assertEqual([call.args[0] for call in seed.call_args_list], ['seed_synthetic', 'seed_workspace'])
