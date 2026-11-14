"""Drift gates for decomposition, not proof of independent business services."""

import ast
import json
from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase
from django.urls import get_resolver
from .ownership import route_owner, table_owner, SCHEMAS


class ServiceOwnershipTests(SimpleTestCase):
    def test_all_existing_routes_keep_the_frozen_contract_and_have_an_owner(self):
        manifest = json.loads(
            (settings.BASE_DIR / "contracts/public-api-baseline.json").read_text()
        )
        routes = []
        for pattern in get_resolver().url_patterns:
            view = pattern.callback.view_class
            path = "/" + str(pattern.pattern)
            methods = sorted(
                m.upper()
                for m in view.http_method_names
                if m not in ("head", "options") and hasattr(view, m)
            )
            self.assertIn(route_owner(path), [*SCHEMAS, "platform_contract"])
            routes.append({"path": path, "methods": methods})
        self.assertEqual(routes, manifest["routes"])
        self.assertEqual(len(routes), 38)

    def test_models_and_auto_created_tables_have_explicit_owners(self):
        for model in apps.get_models(include_auto_created=True):
            self.assertIn(table_owner(model._meta.db_table), SCHEMAS)
        self.assertEqual(table_owner("clients_prospect"), "client_crm")
        self.assertEqual(table_owner("clients_interaction"), "client_crm")
        self.assertEqual(table_owner("clients_opportunity"), "commercial")

    def test_unknown_ownership_is_rejected(self):
        for value, function in [
            ("unclassified_table", table_owner),
            ("/future/secret/", route_owner),
        ]:
            with self.assertRaises(ValueError):
                function(value)

    def test_iam_policy_runtime_cannot_import_client_orm_or_object_scoping(self):
        tree = ast.parse(
            (settings.BASE_DIR / "identity/policies.py").read_text(encoding="utf-8")
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertFalse((node.module or "").startswith("clients"))
            if isinstance(node, ast.Import):
                self.assertFalse(
                    any(alias.name.startswith("clients") for alias in node.names)
                )
        from clients.policies import client_queryset

        self.assertEqual(client_queryset.__module__, "clients.policies")
