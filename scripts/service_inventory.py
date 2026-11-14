"""Export architecture metadata only; never export records or credentials."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".tools/python"), str(ROOT / "backend")]


def inventory():
    import django

    django.setup()
    from django.apps import apps
    from django.db import connection
    from django.db.migrations.loader import MigrationLoader
    from django.urls import get_resolver
    from service_architecture.ownership import table_owner, route_owner, SCHEMAS

    # The only SQL in this command is catalog metadata, under READ ONLY.
    with connection.cursor() as cursor:
        cursor.execute("BEGIN TRANSACTION READ ONLY")
        try:
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            )
            tables = [
                {"table": row[0], "target_owner": table_owner(row[0])}
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """SELECT c.conname, s.relname, t.relname, pg_get_constraintdef(c.oid)
                FROM pg_constraint c JOIN pg_class s ON s.oid=c.conrelid
                JOIN pg_class t ON t.oid=c.confrelid JOIN pg_namespace n ON n.oid=s.relnamespace
                WHERE c.contype='f' AND n.nspname='public' ORDER BY s.relname,c.conname"""
            )
            fks = [
                {
                    "constraint": name,
                    "from": source,
                    "to": target,
                    "definition": definition,
                    "cross_boundary": table_owner(source) != table_owner(target),
                }
                for name, source, target, definition in cursor.fetchall()
            ]
        finally:
            cursor.execute("ROLLBACK")
    models = []
    for model in apps.get_models():
        models.append(
            {
                "model": model._meta.label,
                "table": model._meta.db_table,
                "target_owner": table_owner(model._meta.db_table),
                "relations": [
                    {"field": f.name, "target": f.related_model._meta.label}
                    for f in model._meta.fields
                    if f.is_relation
                ],
            }
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
        routes.append(
            {
                "path": path,
                "methods": methods,
                "target_owner": route_owner(path),
                "current_view": view.__module__ + "." + view.__name__,
            }
        )
    loader = MigrationLoader(None)
    migrations = [
        {"app": app, "name": name, "dependencies": migration.dependencies}
        for (app, name), migration in sorted(loader.disk_migrations.items())
        if app in ("identity", "clients", "ingestion", "audit")
    ]
    return {
        "version": 1,
        "status": "target-not-cut-over",
        "schemas": SCHEMAS,
        "tables": tables,
        "models": models,
        "foreign_keys": fks,
        "routes": routes,
        "historical_migrations": migrations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--env-file", type=Path, default=ROOT / ".local/postgres/env.json"
    )
    options = parser.parse_args()
    os.environ.update(json.loads(options.env_file.read_text()))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    options.output.write_text(
        json.dumps(inventory(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("Architecture metadata written (no record data).")


if __name__ == "__main__":
    main()
