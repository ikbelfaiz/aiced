from django.apps import apps
from django.conf import settings
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase
from django.urls import resolve, Resolver404
from rest_framework.exceptions import ValidationError
from iam_service.private import QueryInput, ReferenceInput


class BoundaryTests(SimpleTestCase):
    def test_no_business_models_registered(self):
        self.assertTrue(settings.IAM_OWNED)
        self.assertFalse(apps.is_installed("clients"))
        self.assertFalse(apps.is_installed("ingestion"))
        self.assertFalse(apps.is_installed("integration_store"))

    def test_independent_migration_lineage(self):
        loader = MigrationLoader(None)
        self.assertIn(("identity", "0001_initial"), loader.disk_migrations)
        self.assertNotIn(
            ("identity", "0003_internal_authorization"), loader.disk_migrations
        )
        self.assertNotIn("clients", {app for app, _ in loader.disk_migrations})

    def test_public_business_paths_absent(self):
        for path in [
            "/api/clients/",
            "/api/imports/context/",
            "/internal/v1/clients/authorize",
        ]:
            with self.assertRaises(Resolver404):
                resolve(path)

    def test_incomplete_journal_cursor_invalid(self):
        data = {
            "credentials": {
                "session_key": "a" * 32,
                "method": "GET",
                "host": "localhost",
                "scheme": "http",
            },
            "limit": 100,
            "before_id": "11111111-1111-1111-1111-111111111111",
        }
        self.assertFalse(QueryInput(data=data).is_valid())

    def test_journal_and_reference_requests_bounded(self):
        self.assertFalse(QueryInput(data={"limit": 101}).is_valid())
        self.assertFalse(
            ReferenceInput(
                data={"membership_ids": ["11111111-1111-1111-1111-111111111111"] * 101}
            ).is_valid()
        )
