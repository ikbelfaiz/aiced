"""M1 safety gate: synthetic PostgreSQL backup/restore and consumer tests.

The existing database is read-only. Only generated, marked scratch databases
may receive migrations, fixtures, tests, browser writes or cleanup.
"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".tools/python"), str(ROOT / "backend")]
import psycopg
from psycopg import sql
from testing.rehearsal import validate_environment


def canonical_constraint(definition):
    """Recognize only PostgreSQL's equivalent text-array constant cast forms.

    pg_dump/reparse moves ::text[] from the constant array to each literal.
    Preserve the entire expression, column and values; no generic stripping of
    casts, predicates or whitespace that could conceal a weakened constraint.
    """
    match = re.match(r"CHECK \(\(\((\w+)\)::text = ANY ", definition)
    if not match:
        return definition
    column = match.group(1)
    values = re.findall(r"'([a-z_]+)'::character varying", definition)
    source = (
        f"CHECK ((({column})::text = ANY ((ARRAY["
        + ", ".join(f"'{v}'::character varying" for v in values)
        + "])::text[])))"
    )
    restored = (
        f"CHECK ((({column})::text = ANY (ARRAY["
        + ", ".join(f"('{v}'::character varying)::text" for v in values)
        + "])))"
    )
    if values and definition in (source, restored):
        return "CHECK_TEXT_MEMBERSHIP:" + json.dumps([column, values])
    return definition


def connection_args(env, database=None):
    return dict(
        host=env["POSTGRES_HOST"],
        port=env.get("POSTGRES_PORT", "5432"),
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
        dbname=database or env["POSTGRES_DB"],
        connect_timeout=5,
    )


def fingerprint(env):
    """Sorted private digests, schema and sequence state in one read-only snapshot."""
    with psycopg.connect(**connection_args(env)) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            )
        ]
        result = {"tables": {}}
        for table in tables:
            digest = hashlib.sha256()
            count = 0
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "SELECT to_jsonb(t)::text FROM public.{} t ORDER BY to_jsonb(t)::text"
                    ).format(sql.Identifier(table))
                )
                for row in cursor:
                    data = row[0].encode("utf-8")
                    digest.update(len(data).to_bytes(8, "big"))
                    digest.update(data)
                    count += 1
            result["tables"][table] = {"count": count, "sha256": digest.hexdigest()}
        queries = {
            "columns": "SELECT table_name,column_name,udt_name,is_nullable,column_default,is_identity,is_generated FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position",
            "constraints": "SELECT r.relname,c.conname,pg_get_constraintdef(c.oid),c.convalidated FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='public' ORDER BY r.relname,c.conname",
            "indexes": "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname",
            "triggers": "SELECT r.relname,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled FROM pg_trigger t JOIN pg_class r ON r.oid=t.tgrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY r.relname,t.tgname",
            "functions": "SELECT p.proname,pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prokind='f' ORDER BY p.proname,pg_get_function_identity_arguments(p.oid)",
            "ownership_acl": "SELECT c.relname,pg_get_userbyid(c.relowner),c.relacl::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','S') ORDER BY c.relname",
        }
        for name, query in queries.items():
            result[name] = [list(row) for row in conn.execute(query)]
        for row in result["constraints"]:
            row[2] = canonical_constraint(row[2])
        result["sequences"] = {}
        for (name,) in conn.execute(
            "SELECT sequencename FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename"
        ):
            row = conn.execute(
                sql.SQL("SELECT last_value,is_called FROM public.{}").format(
                    sql.Identifier(name)
                )
            ).fetchone()
            result["sequences"][name] = list(row)
        return result


def require_equal(before, after, label):
    if before != after:
        changed = [
            key
            for key in before.keys() | after.keys()
            if before.get(key) != after.get(key)
        ]
        raise RuntimeError(f"{label}: mismatch in {changed}; no cutover permitted.")


def verify_restored_constraints(env):
    """Probe the actual restored database, always rolling back each attempt."""
    name = validate_environment(env)
    if not name.endswith("_restore"):
        raise ValueError(
            "Integrity probes are permitted only on the restored scratch database."
        )
    probes = {
        "audit_append_only": ("UPDATE audit_auditevent SET action=action", "23514"),
        "staging_immutable": ("UPDATE ingestion_stagingrow SET cells=cells", "P0001"),
        "snapshots_immutable": (
            "UPDATE ingestion_sourcesnapshot SET external_key=external_key",
            "P0001",
        ),
        "assignment_same_org": (
            "UPDATE clients_party p SET assigned_to_id=(SELECT id FROM identity_membership m WHERE m.organization_id<>p.organization_id ORDER BY id LIMIT 1) WHERE p.id=(SELECT id FROM clients_party ORDER BY id LIMIT 1)",
            "23503",
        ),
        "deferred_subtype": (
            "UPDATE clients_party SET kind='legal' WHERE kind='physical'",
            "23514",
        ),
        "crm_notes_length": (
            "UPDATE clients_crmprofile SET notes=repeat('x',5001)",
            "23514",
        ),
        "financial_source_unique": (
            "INSERT INTO clients_financialaccount(id,party_id,source,external_id,source_as_of,product_label) SELECT gen_random_uuid(),party_id,source,external_id,source_as_of,product_label FROM clients_financialaccount LIMIT 1",
            "23505",
        ),
        "publication_consistent": (
            "UPDATE ingestion_importbatch SET published_at=NULL WHERE status='published'",
            "23514",
        ),
        "separate_approver": (
            "UPDATE ingestion_importpolicy SET approved_by_id=created_by_id",
            "23514",
        ),
    }
    with psycopg.connect(**connection_args(env), autocommit=True) as conn:
        for label, (statement, expected) in probes.items():
            try:
                with conn.transaction():
                    conn.execute(statement)
                    conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
                    raise RuntimeError(
                        f"Restored constraint {label} did not reject the probe."
                    )
            except psycopg.Error as exc:
                if exc.sqlstate != expected:
                    raise RuntimeError(
                        f"Restored constraint {label}: unexpected SQLSTATE {exc.sqlstate}."
                    ) from exc
    return list(probes)


class ScratchDatabases:
    def __init__(self, env, protected):
        self.env, self.protected, self.created = env, protected, []

    def check_name(self, name):
        validate_environment(self.env, name)
        if name == self.protected:
            raise ValueError("The existing database is protected.")

    def create(self, name):
        self.check_name(name)
        with psycopg.connect(
            **connection_args(self.env, "postgres"), autocommit=True
        ) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            self.created.append(name)
            conn.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(name),
                    sql.Literal("aiced-m1:" + self.env["AICED_REHEARSAL_RUN"]),
                )
            )

    def drop(self, name):
        self.check_name(name)
        if name not in self.created:
            raise ValueError("Cannot drop a database not created by this process.")
        with psycopg.connect(
            **connection_args(self.env, "postgres"), autocommit=True
        ) as conn:
            marker = conn.execute(
                "SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=%s",
                (name,),
            ).fetchone()
            if not marker or marker[0] != "aiced-m1:" + self.env["AICED_REHEARSAL_RUN"]:
                raise ValueError("Database marker mismatch; cleanup refused.")
            conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
        self.created.remove(name)


def pg_binary(name):
    local = ROOT / ".tools/pgsql/bin" / (name + (".exe" if os.name == "nt" else ""))
    binary = str(local) if local.exists() else shutil.which(name)
    if not binary:
        raise RuntimeError(
            f"{name} is required; install matching PostgreSQL client tools."
        )
    return binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-synthetic", action="store_true", required=True)
    parser.add_argument('--gateway', action='store_true', help='Run M2 real-Nginx contracts and browsers through the gateway.')
    parser.add_argument(
        "--env-file", type=Path, default=ROOT / ".local/postgres/env.json"
    )
    parser.add_argument(
        "--skip-browser",
        action="store_true",
        help="Partial check only; cannot satisfy the full M1 gate.",
    )
    options = parser.parse_args()
    original = json.loads(options.env_file.read_text())
    run = uuid.uuid4().hex
    env = {key: value for key, value in original.items() if key.startswith("POSTGRES_")}
    env.update(
        DJANGO_DEBUG=original.get("DJANGO_DEBUG"),
        POSTGRES_DB=f"aiced_m1_{run}_source",
        AICED_REHEARSAL_RUN=run,
        DJANGO_SECRET_KEY=secrets.token_urlsafe(50),
        DJANGO_ALLOWED_HOSTS="testserver,localhost,127.0.0.1",
    )
    validate_environment(env)
    dump_binary, restore_binary = pg_binary("pg_dump"), pg_binary("pg_restore")
    directory = ROOT / ".local/migration-baseline" / run
    directory.mkdir(parents=True, mode=0o700)
    state_file = directory / "synthetic-session.json"
    password_file = directory / "synthetic-password"
    password_file.write_text(secrets.token_urlsafe(36))
    child = {
        **os.environ,
        **env,
        "PYTHONPATH": str(ROOT / ".tools/python"),
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "AICED_SEED_PASSWORD": password_file.read_text(),
        "PGPASSWORD": env["POSTGRES_PASSWORD"],
    }
    source = env["POSTGRES_DB"]
    restored = f"aiced_m1_{run}_restore"
    scratch = ScratchDatabases(env, original["POSTGRES_DB"])
    summary = {
        "run": run,
        "status": "running",
        "database_ownership_moved": False,
        "gateway_enabled": options.gateway,
        "browser_skipped": options.skip_browser,
        "steps": [],
    }

    def save(name, value):
        (directory / name).write_text(
            json.dumps(value, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def execute(label, args, database=source):
        validate_environment(env, database)
        print(label, flush=True)
        with (directory / (label + ".log")).open("wb") as log:
            result = subprocess.run(
                args,
                cwd=ROOT,
                env={**child, "POSTGRES_DB": database},
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        summary["steps"].append({"name": label, "exit_code": result.returncode})
        if result.returncode:
            raise RuntimeError(
                f'{label} failed; see private log {directory / (label+".log")}'
            )

    def django(label, *args, database=source):
        execute(
            label, [sys.executable, str(ROOT / "backend/manage.py"), *args], database
        )

    before = fingerprint(original)
    save("existing-before.json", before)
    try:
        scratch.create(source)
        scratch.create(restored)
        django("migrate-synthetic", "migrate", "--noinput")
        django(
            "prepare-synthetic",
            "migration_rehearsal_fixture",
            "--state-file",
            str(state_file),
        )
        baseline = fingerprint(env)
        save("synthetic-before.json", baseline)
        backup = directory / "synthetic.dump"
        pg_args = [
            "--host",
            env["POSTGRES_HOST"],
            "--port",
            env.get("POSTGRES_PORT", "5432"),
            "--username",
            env["POSTGRES_USER"],
        ]
        execute(
            "pg-dump",
            [
                dump_binary,
                *pg_args,
                "--format=custom",
                "--file",
                str(backup),
                "--dbname",
                source,
            ],
        )
        execute(
            "pg-restore",
            [
                restore_binary,
                *pg_args,
                "--exit-on-error",
                "--dbname",
                restored,
                str(backup),
            ],
            restored,
        )
        restored_env = {**env, "POSTGRES_DB": restored}
        restored_state = fingerprint(restored_env)
        save("synthetic-restored.json", restored_state)
        require_equal(baseline, restored_state, "Restoration parity")
        summary["restoration_equal"] = True
        summary["backup_sha256"] = hashlib.sha256(backup.read_bytes()).hexdigest()
        summary["synthetic_counts"] = {
            table: value["count"] for table, value in baseline["tables"].items()
        }
        summary["restored_constraint_probes"] = verify_restored_constraints(
            restored_env
        )
        require_equal(
            restored_state, fingerprint(restored_env), "Constraint probes rolled back"
        )
        django(
            "verify-restored-session",
            "migration_rehearsal_fixture",
            "--verify",
            "--state-file",
            str(state_file),
            database=restored,
        )
        require_equal(
            restored_state, fingerprint(restored_env), "Read-only restored verification"
        )
        django("django-check", "check", database=restored)
        django(
            "migration-consistency",
            "makemigrations",
            "--check",
            "--dry-run",
            database=restored,
        )
        django(
            "openapi",
            "spectacular",
            "--file",
            str(directory / "openapi.yaml"),
            "--validate",
            "--fail-on-warn",
            database=restored,
        )
        django(
            "backend-tests",
            "test",
            "core",
            "identity",
            "clients",
            "ingestion",
            "audit",
            "contracts",
            "service_architecture",
            "internal_api",
            "--noinput",
            database=restored,
        )
        if options.gateway:
            django('gateway-tests', 'test', 'gateway_tests', '--noinput', database=restored)
        if not options.skip_browser:
            node = (
                str(ROOT / ".tools/node.exe")
                if (ROOT / ".tools/node.exe").exists()
                else shutil.which("node")
            )
            if not node:
                raise RuntimeError("Node is required for the browser gate.")
            execute(
                "frontend-build",
                [
                    node,
                    str(ROOT / "frontend/node_modules/typescript/bin/tsc"),
                    "--noEmit",
                    "--project",
                    str(ROOT / "frontend/tsconfig.json"),
                ],
                restored,
            )
            execute(
                "frontend-bundle",
                [
                    node,
                    str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                    "build",
                    str(ROOT / "frontend"),
                ],
                restored,
            )
            environment_file = directory / "restored-env.json"
            save("restored-env.json", restored_env)
            for mode, extra in [
                ("browser-dev", ["--grep-invert", "production build"]),
                (
                    "browser-bundle",
                    [
                        "--production",
                        "--grep",
                        "production build|Client 360|Data Management|Prospects",
                    ],
                ),
            ]:
                execute(
                    mode,
                    [
                        sys.executable,
                        str(ROOT / "scripts/frontend_e2e.py"),
                        "--rehearsal-env",
                        str(environment_file),
                        "--rehearsal-password",
                        str(password_file),
                        "--report-directory",
                        str(directory / mode),
                        *(['--gateway'] if options.gateway else []),
                        *extra,
                    ],
                    restored,
                )
        summary["status"] = (
            "passed" if not options.skip_browser else "partial-backend-only"
        )
    except Exception as exc:
        summary["status"] = "failed"
        summary["error"] = str(exc)
        raise
    finally:
        errors = []
        try:
            after = fingerprint(original)
            save("existing-after.json", after)
            summary["existing_database_unchanged"] = before == after
            require_equal(before, after, "Existing database preservation")
        except Exception as exc:
            errors.append(str(exc))
        for name in list(reversed(scratch.created)):
            try:
                scratch.drop(name)
            except Exception as exc:
                errors.append(f"Cleanup refused/failed for {name}: {exc}")
        summary["scratch_databases_removed"] = not scratch.created
        if errors:
            summary["status"] = "failed"
            summary["finalization_errors"] = errors
        save("report.json", summary)
        if errors:
            raise RuntimeError(
                "Rehearsal finalization failed; preserve artifacts and inspect the private report."
            )
    print(
        f'{"M2" if options.gateway else "M1"} {summary["status"]}; private report: {directory / "report.json"}',
        flush=True,
    )


if __name__ == "__main__":
    main()
