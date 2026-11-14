"""Isolated Commercial graph and trust tests; process/SQL proofs live in S6 gate."""

from django.apps import apps
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase
from django.core.exceptions import ImproperlyConfigured
from commercial.contracts import OpportunityInput
from iam_consumer.trust import validate
from internal_api.client import InternalClient


class BoundaryTests(SimpleTestCase):
    def test_only_owned_models_registered(self):
        self.assertEqual(
            {m._meta.app_label for m in apps.get_models()}, {"commercial_store"}
        )

    def test_only_owned_migration_lineage(self):
        loader = MigrationLoader(None)
        self.assertEqual(
            {app for app, name in loader.disk_migrations}, {"commercial_store"}
        )

    def test_strict_fields_and_exact_estimates(self):
        for fields in [
            {"author_id": "forged"},
            {"organization_id": "forged"},
            {"party_id": "forged"},
            {"amount": "NaN"},
            {"amount": "1.0001"},
            {"amount": "-1"},
        ]:
            self.assertFalse(
                OpportunityInput(data={"title": "Synthetic", **fields}).is_valid()
            )
        data = OpportunityInput(data={"title": "Synthetic", "amount": "123.456"})
        self.assertTrue(data.is_valid())
        self.assertEqual(str(data.validated_data["amount"]), "123.456")

    def test_ingress_cannot_become_client_outbound_identity(self):
        own = {"service": "client_crm", "audiences": ["iam"]}
        validate(
            {"own": own, "peer": {"service": "commercial", "audiences": ["client"]}},
            "own",
        )
        for peer in [
            {"service": "commercial", "audiences": ["iam", "client"]},
            {"service": "iam", "audiences": ["client"]},
            {"service": "client_crm", "audiences": ["client"]},
        ]:
            with self.assertRaises(ImproperlyConfigured):
                validate({"own": own, "peer": peer}, "own")
        with self.assertRaises(ImproperlyConfigured):
            validate(
                {"peer": {"service": "commercial", "audiences": ["client"]}}, "peer"
            )

    def test_cleartext_internal_transport_is_loopback_only(self):
        with self.assertRaises(ValueError):
            InternalClient("http://remote.example", "key", "secret", "client")
