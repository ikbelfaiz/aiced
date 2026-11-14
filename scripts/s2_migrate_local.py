"""Apply ONLY S2 additive migrations to the portable local development DB.

First dump/restore and migrate a marked scratch copy. Never reset/drop the
application database, move business tables, or automatically restore over it.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / ".tools/python"),
    str(ROOT / "backend"),
    str(ROOT / "scripts"),
]
from migration_baseline import (
    fingerprint,
    require_equal,
    ScratchDatabases,
    connection_args,
)
import psycopg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-local-additive", required=True, action="store_true")
    options = parser.parse_args()
    original = json.loads((ROOT / ".local/postgres/env.json").read_text())
    if (
        original.get("POSTGRES_HOST") != "127.0.0.1"
        or str(original.get("POSTGRES_PORT")) != "55432"
        or original.get("DJANGO_DEBUG") != "1"
    ):
        raise ValueError(
            "Only the existing portable local development cluster is supported"
        )
    os.environ.update(original)
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django

    django.setup()
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    pending = {
        (migration.app_label, migration.name)
        for migration, backwards in executor.migration_plan(
            executor.loader.graph.leaf_nodes()
        )
    }
    expected = {
        ("identity", "0003_internal_authorization"),
        ("audit", "0004_audit_outbox"),
    }
    if not pending:
        print("S2 local migrations already applied; no changes.")
        return
    if pending != expected:
        raise ValueError("Unexpected migration plan; local application refused")
    run = uuid.uuid4().hex
    directory = ROOT / ".local/s2-local-migration" / run
    directory.mkdir(parents=True, mode=0o700)
    env = {
        **original,
        "AICED_REHEARSAL_RUN": run,
        "POSTGRES_DB": f"aiced_m1_{run}_restore",
    }
    scratch = ScratchDatabases(env, original["POSTGRES_DB"])
    report = {
        "status": "running",
        "business_tables_moved": False,
        "scratch_removed": False,
    }
    before = fingerprint(original)

    def metadata_rows(database_env):
        with psycopg.connect(**connection_args(database_env)) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            return {
                table: [
                    row[0]
                    for row in conn.execute(
                        "SELECT to_jsonb(t) FROM public." + table + " t ORDER BY id"
                    )
                ]
                for table in ("auth_permission", "django_content_type")
            }

    original_metadata = metadata_rows(original)
    (directory / "before.json").write_text(json.dumps(before, indent=2))
    child = {
        **os.environ,
        "PGPASSWORD": original["POSTGRES_PASSWORD"],
        "PYTHONPATH": str(ROOT / ".tools/python"),
    }
    pg = [
        "--host",
        original["POSTGRES_HOST"],
        "--port",
        str(original["POSTGRES_PORT"]),
        "--username",
        original["POSTGRES_USER"],
    ]

    def run_command(label, args, database=None):
        with (directory / (label + ".log")).open("wb") as log:
            subprocess.run(
                args,
                check=True,
                env={**child, "POSTGRES_DB": database or original["POSTGRES_DB"]},
                cwd=ROOT,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

    def migrate(database):
        run_command(
            "migrate-" + database,
            [sys.executable, str(ROOT / "backend/manage.py"), "migrate", "--noinput"],
            database,
        )

    def unchanged_records(state, database_env):
        for table, values in before["tables"].items():
            if table not in (
                "django_migrations",
                "auth_permission",
                "django_content_type",
            ):
                require_equal(
                    values, state["tables"][table], table + " record preservation"
                )
        metadata = metadata_rows(database_env)
        for table, rows in original_metadata.items():
            if not all(row in metadata[table] for row in rows):
                raise RuntimeError("Existing Django metadata changed: " + table)
        new_types = [
            row
            for row in metadata["django_content_type"]
            if row not in original_metadata["django_content_type"]
        ]
        allowed = {
            ("identity", "internalnonce"),
            ("audit", "auditoutbox"),
            ("audit", "auditreceipt"),
        }
        if {(row["app_label"], row["model"]) for row in new_types} != allowed:
            raise RuntimeError("Unexpected new Django content types")
        ids = {row["id"] for row in new_types}
        new_permissions = [
            row
            for row in metadata["auth_permission"]
            if row not in original_metadata["auth_permission"]
        ]
        if len(new_permissions) != 12 or any(
            row["content_type_id"] not in ids for row in new_permissions
        ):
            raise RuntimeError("Unexpected new Django model permissions")
        for name in ("constraints", "indexes", "columns", "ownership_acl"):
            if not all(row in state[name] for row in before[name]):
                raise RuntimeError("Existing metadata changed: " + name)

    try:
        dump = directory / "before-s2.dump"
        run_command(
            "dump",
            [
                str(ROOT / ".tools/pgsql/bin/pg_dump.exe"),
                *pg,
                "--format=custom",
                "--file",
                str(dump),
                original["POSTGRES_DB"],
            ],
        )
        scratch.create(env["POSTGRES_DB"])
        run_command(
            "restore",
            [
                str(ROOT / ".tools/pgsql/bin/pg_restore.exe"),
                *pg,
                "--exit-on-error",
                "--dbname",
                env["POSTGRES_DB"],
                str(dump),
            ],
        )
        require_equal(
            before, fingerprint(env), "Existing local backup restoration parity"
        )
        migrate(env["POSTGRES_DB"])
        unchanged_records(fingerprint(env), env)
        require_equal(
            before,
            fingerprint(original),
            "No concurrent application writes before local migration",
        )
        migrate(original["POSTGRES_DB"])
        after = fingerprint(original)
        unchanged_records(after, original)
        (directory / "after.json").write_text(json.dumps(after, indent=2))
        report.update(
            status="passed",
            backup_restore_equal=True,
            existing_records_unchanged=True,
            backup_sha256=hashlib.sha256(dump.read_bytes()).hexdigest(),
            new_tables=sorted(set(after["tables"]) - set(before["tables"])),
        )
    except Exception:
        report["status"] = "failed"
        raise
    finally:
        try:
            for name in list(scratch.created):
                scratch.drop(name)
            report["scratch_removed"] = True
        except Exception:
            report["status"] = "failed"
            raise
        finally:
            (directory / "report.json").write_text(json.dumps(report, indent=2))
    print(
        f'S2 local additive migration {report["status"]}; private report: {directory / "report.json"}'
    )


if __name__ == "__main__":
    main()
