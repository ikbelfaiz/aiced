"""Controlled portable-development cutover/rollback. Never accepts production.

Backup and disposable restore precede ownership changes. Both writers are frozen
for copies. Published/staged state and immutable audit are retained on rollback.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / ".tools/python"),
    str(ROOT / "backend"),
    str(ROOT / "scripts"),
]
import psycopg
from psycopg import sql
from migration_baseline import (
    fingerprint,
    require_equal,
    connection_args,
    ScratchDatabases,
    pg_binary,
    canonical_constraint,
)
from s3_database import provision, grant_runtime, SCHEMA, TABLES
from s4_transfer import freeze, activate, transfer, fence_legacy


def permissions(conn):
    """Compare effective grants, including owner/default ACL equivalence.

    pg_dump legitimately omits an explicit ACL equal to the PostgreSQL default.
    Preserve owners, grantors, grantees, each privilege and grant option; never
    strip arbitrary ACL differences or treat all owner ACLs as equivalent.
    """
    return {
        'columns':list(conn.execute("""SELECT n.nspname,c.relname,v.attname,pg_get_userbyid(a.grantor),
            CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable
            FROM pg_attribute v JOIN pg_class c ON c.oid=v.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            CROSS JOIN LATERAL aclexplode(v.attacl) a
            WHERE n.nspname IN ('public','aiced_integration') AND NOT v.attisdropped ORDER BY 1,2,3,4,5,6,7""")),
        "owners": list(
            conn.execute(
                "SELECT n.nspname,c.relname,pg_get_userbyid(c.relowner) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','aiced_integration') AND c.relkind IN ('r','S') ORDER BY 1,2"
            )
        ),
        "tables": list(
            conn.execute(
                """SELECT n.nspname,c.relname,pg_get_userbyid(a.grantor),
            CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault(CASE WHEN c.relkind='S' THEN 'S'::\"char\" ELSE 'r'::\"char\" END,c.relowner))) a
            WHERE n.nspname IN ('public','aiced_integration') AND c.relkind IN ('r','S') ORDER BY 1,2,3,4,5,6"""
            )
        ),
        "schemas": list(
            conn.execute(
                """SELECT n.nspname,pg_get_userbyid(n.nspowner),pg_get_userbyid(a.grantor),
            CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable
            FROM pg_namespace n CROSS JOIN LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a
            WHERE n.nspname IN ('public','aiced_integration') ORDER BY 1,2,3,4,5,6"""
            )
        ),
        "functions": list(
            conn.execute(
                """SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),pg_get_userbyid(p.proowner),
            pg_get_userbyid(a.grantor),CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
            WHERE n.nspname IN ('public','aiced_integration') ORDER BY 1,2,3,4,5,6,7,8"""
            )
        ),
    }


def owned_metadata(conn):
    result={}
    for name,query in {
        'columns':"SELECT table_name,column_name,udt_name,is_nullable,column_default,is_identity,is_generated FROM information_schema.columns WHERE table_schema='aiced_integration' ORDER BY table_name,ordinal_position",
        'constraints':"SELECT c.relname,k.conname,pg_get_constraintdef(k.oid),k.convalidated FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='aiced_integration' ORDER BY 1,2",
        'indexes':"SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='aiced_integration' ORDER BY 1,2",
        'triggers':"SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='aiced_integration' AND NOT t.tgisinternal ORDER BY 1,2",
        'functions':"SELECT p.proname,pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='aiced_integration' AND p.prokind='f' ORDER BY p.proname,pg_get_function_identity_arguments(p.oid)"}.items():
        result[name]=[list(row) for row in conn.execute(query)]
    for row in result['constraints']:row[2]=canonical_constraint(row[2])
    result['sequences']={}
    for (name,) in conn.execute("SELECT sequencename FROM pg_sequences WHERE schemaname='aiced_integration' ORDER BY 1"):
        result['sequences'][name]=list(conn.execute(sql.SQL('SELECT last_value,is_called FROM {}.{}').format(sql.Identifier(SCHEMA),sql.Identifier(name))).fetchone())
    return result


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)


def run(label, args, env, directory):
    with (directory / (label + ".log")).open("wb") as log:
        subprocess.run(
            args,
            env={**os.environ, **env, "PYTHONPATH": str(ROOT / ".tools/python")},
            cwd=ROOT,
            stdout=log,
            stderr=log,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )


def backup_restore(original, admin, directory, label):
    marker = uuid.uuid4().hex
    target = f"aiced_m1_{marker}_restore"
    scratchenv = {**original, "POSTGRES_DB": target, "AICED_REHEARSAL_RUN": marker}
    scratch = ScratchDatabases(scratchenv, original["POSTGRES_DB"])
    pg = [
        "--host",
        admin["POSTGRES_HOST"],
        "--port",
        str(admin["POSTGRES_PORT"]),
        "--username",
        admin["POSTGRES_USER"],
    ]
    child = {**admin, "PGPASSWORD": admin["POSTGRES_PASSWORD"]}
    backup = directory / (label + ".dump")
    try:
        scratch.create(target)
        with psycopg.connect(**connection_args(admin)) as exporter:
            exporter.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            snapshot = exporter.execute("SELECT pg_export_snapshot()").fetchone()[0]
            before = fingerprint(admin, snapshot=snapshot)
            before_permissions = permissions(exporter)
            before_owned_metadata=owned_metadata(exporter)
            # Include all owned table values in the same exported snapshot.
            owned = {}
            for (table,) in exporter.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname=%s ORDER BY tablename",
                (SCHEMA,),
            ):
                rows = exporter.execute(
                    sql.SQL(
                        "SELECT to_jsonb(t)::text FROM {}.{} t ORDER BY to_jsonb(t)::text"
                    ).format(sql.Identifier(SCHEMA), sql.Identifier(table))
                ).fetchall()
                owned[table] = hashlib.sha256(json.dumps(rows).encode()).hexdigest()
            run(
                label + "-dump",
                [
                    pg_binary("pg_dump"),
                    *pg,
                    "--snapshot",
                    snapshot,
                    "--format=custom",
                    "--file",
                    str(backup),
                    "--dbname",
                    original["POSTGRES_DB"],
                ],
                child,
                directory,
            )
        run(
            label + "-restore",
            [
                pg_binary("pg_restore"),
                *pg,
                "--exit-on-error",
                "--dbname",
                target,
                str(backup),
            ],
            child,
            directory,
        )
        restored = {**admin, "POSTGRES_DB": target}
        restored_fingerprint = fingerprint(restored)
        with psycopg.connect(**connection_args(restored)) as c:
            require_equal(
                before_permissions,
                permissions(c),
                "Local backup/restore owners and effective privileges",
            )
            require_equal(before_owned_metadata,owned_metadata(c),'Local backup/restore owned metadata and sequence state')
            # ACL text itself can be NULL or explicit-default. Every effective
            # grant was checked above, while all other metadata stays exact.
            before.pop("ownership_acl")
            restored_fingerprint.pop("ownership_acl")
            require_equal(
                before, restored_fingerprint, "Local backup/restore public parity"
            )
            for table, digest in owned.items():
                rows = c.execute(
                    sql.SQL(
                        "SELECT to_jsonb(t)::text FROM {}.{} t ORDER BY to_jsonb(t)::text"
                    ).format(sql.Identifier(SCHEMA), sql.Identifier(table))
                ).fetchall()
                if hashlib.sha256(json.dumps(rows).encode()).hexdigest() != digest:
                    raise ValueError("Owned backup restore mismatch")
        return {
            "backup": str(backup),
            "sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
            "restoration_verified": True,
        }
    finally:
        for name in list(scratch.created):
            scratch.drop(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-local-cutover", action="store_true", required=True)
    parser.add_argument("--verification-report", type=Path)
    parser.add_argument(
        "--rollback",
        type=Path,
        help="Private state directory of an already active local cutover",
    )
    parser.add_argument(
        "--forward",
        type=Path,
        help="Re-cut over an existing local deployment after rollback",
    )
    args = parser.parse_args()
    original = json.loads((ROOT / ".local/postgres/env.json").read_text())
    if (
        original.get("DJANGO_DEBUG") != "1"
        or original.get("POSTGRES_HOST") != "127.0.0.1"
        or str(original.get("POSTGRES_PORT")) != "55432"
        or original.get("POSTGRES_DB") != "aiced"
    ):
        raise ValueError(
            "This tool supports ONLY the existing portable local development database"
        )
    admin = {
        **original,
        "POSTGRES_USER": "aiced_owner",
        "POSTGRES_PASSWORD": json.loads(
            (ROOT / ".local/postgres/credentials.json").read_text()
        )["owner"],
    }
    if args.rollback and args.forward:
        raise ValueError("Select one direction")
    if args.rollback or args.forward:
        directory = (args.rollback or args.forward).resolve()
        if not directory.is_relative_to((ROOT / ".local/s4-active").resolve()):
            raise ValueError("Unknown state directory")
        state = json.loads((directory / "state.json").read_text())
        spec = json.loads((directory / "ownership-private.json").read_text())
        with psycopg.connect(**connection_args(admin), autocommit=True) as c:
            freeze(c)
        direction = "rollback" if args.rollback else "forward"
        state[direction + "_backup"] = backup_restore(
            original,
            admin,
            directory,
            "before-" + direction + "-" + uuid.uuid4().hex[:8],
        )
        write(directory / "state.json", state)
        with psycopg.connect(**connection_args(admin), autocommit=True) as c:
            transfer(
                c,
                SCHEMA if args.rollback else "public",
                "public" if args.rollback else SCHEMA,
            )
            with c.transaction():
                fence_legacy(
                    c,
                    {**original, "AICED_REHEARSAL_RUN": state["run"]},
                    spec,
                    active=not bool(args.rollback),
                )
                activate(c, "public" if args.rollback else SCHEMA)
        deployment = json.loads((directory / "deployment.json").read_text())
        deployment["mode"] = "legacy" if args.rollback else "service"
        write(directory / "deployment.json", deployment)
        state["writer"] = "legacy" if args.rollback else "integration"
        state["status"] = "rolled_back" if args.rollback else "prepared"
        write(directory / "state.json", state)
        print(
            "Local "
            + direction
            + " complete; supervisor will switch Gateway after state transfer. Private state: "
            + str(directory)
        )
        return
    if not args.verification_report:
        raise ValueError("A passed S4 verification report is required")
    evidence = json.loads(args.verification_report.read_text())
    if (
        evidence.get("status") != "passed"
        or evidence.get("final_writer") != "integration"
        or not evidence.get("client_crm_unchanged")
    ):
        raise ValueError("S4 gates did not pass")
    for name, digest in evidence.get("code_sha256", {}).items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Code changed after rehearsal: " + name)
    with psycopg.connect(**connection_args(admin)) as c:
        if c.execute(
            "SELECT 1 FROM pg_namespace WHERE nspname=%s", (SCHEMA,)
        ).fetchone():
            raise ValueError(
                "Owned schema already exists: preserve it and use the saved state/runbook, never replace it"
            )
    run_id = uuid.uuid4().hex
    directory = ROOT / ".local/s4-active" / run_id
    directory.mkdir(parents=True, mode=0o700)
    state = {
        "run": run_id,
        "status": "preparing",
        "writer": "legacy",
        "production": False,
        "verification_report": str(args.verification_report.resolve()),
    }
    write(directory / "state.json", state)
    state["pre_cutover_backup"] = backup_restore(
        original, admin, directory, "before-s4"
    )
    write(directory / "state.json", state)
    verified = True

    def local_guard(c, env):
        if (
            not verified
            or c.execute("SELECT current_database()").fetchone()[0] != "aiced"
        ):
            raise ValueError("Backup verification required")

    localenv = {**original, "AICED_REHEARSAL_RUN": run_id}
    with psycopg.connect(**connection_args(admin), autocommit=True) as c:
        spec = provision(c, localenv, verify=local_guard)
    write(directory / "ownership-private.json", spec)
    keys = {
        "integration-s4": {
            "secret": secrets.token_urlsafe(48),
            "service": "integration",
            "audiences": ["iam", "audit"],
        },
        "iam-integration-s4": {
            "secret": secrets.token_urlsafe(48),
            "service": "iam",
            "audiences": ["integration"],
        },
    }
    gateway = secrets.token_urlsafe(48)
    backend = {
        **original,
        "AICED_GATEWAY_KEY": gateway,
        "AICED_INTERNAL_KEYS": json.dumps(keys),
        "AICED_INTEGRATION_AUDIT_URL": "http://127.0.0.1:8002",
        "AICED_INTEGRATION_AUDIT_KEY_ID": "iam-integration-s4",
    }
    integration = {
        **backend,
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
        "POSTGRES_USER": spec["roles"]["runtime"],
        "POSTGRES_PASSWORD": spec["passwords"]["runtime"],
        "AICED_INTEGRATION_KEY_ID": "integration-s4",
        "AICED_IAM_URL": "http://127.0.0.1:8001",
    }
    # No IAM database credential or Django session secret in the service file.
    write(directory / "backend-env.json", backend)
    write(directory / "integration-env.json", integration)
    migration = {
        **integration,
        "POSTGRES_USER": spec["roles"]["migrator"],
        "POSTGRES_PASSWORD": spec["passwords"]["migrator"],
        "AICED_MIGRATION_ROLE": spec["roles"]["owner"],
    }
    write(directory / "migration-env.json", migration)
    run(
        "legacy-migrate",
        [sys.executable, "backend/manage.py", "migrate", "--noinput"],
        original,
        directory,
    )
    run(
        "integration-migrate",
        [
            sys.executable,
            "backend/integration_service/manage.py",
            "migrate",
            "--noinput",
        ],
        migration,
        directory,
    )
    with psycopg.connect(**connection_args(admin), autocommit=True) as c:
        grant_runtime(c, spec)
        freeze(c)
        state["status"] = "frozen"
        write(directory / "state.json", state)
        state["frozen_backup"] = backup_restore(
            original, admin, directory, "frozen-before-transfer"
        )
        write(directory / "state.json", state)
        transfer(c, "public", SCHEMA)
        with c.transaction():
            fence_legacy(c, localenv, spec)
            activate(c, SCHEMA)
        state["copied_counts"] = {
            table: c.execute(
                sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(SCHEMA), sql.Identifier(table)
                )
            ).fetchone()[0]
            for table in TABLES
        }
    write(directory / "ownership-private.json", spec)
    write(
        directory / "deployment.json",
        {
            "mode": "service",
            "backend_port": 8000,
            "iam_port": 8001,
            "integration_port": 8002,
            "frontend_port": 5174,
            "gateway_port": 5173,
        },
    )
    state.update(status="prepared", writer="integration")
    write(directory / "state.json", state)
    print(
        "Local data cutover prepared. Start scripts/run_s4_deployment.py with private directory: "
        + str(directory)
    )


if __name__ == "__main__":
    main()
