"""Whole local S5 restore verification, including IAM and Integration ownership."""

import hashlib, json, os, subprocess, uuid
from pathlib import Path
import psycopg
from psycopg import sql
from migration_baseline import (
    ScratchDatabases,
    connection_args,
    pg_binary,
    require_equal,
    canonical_constraint,
)

SCHEMAS = ["public", "aiced_integration", "aiced_iam"]


def database_acl(conn):
    owner = conn.execute(
        "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()"
    ).fetchone()[0]
    rights = [
        list(r)
        for r in conn.execute(
            "SELECT pg_get_userbyid(a.grantor),CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable FROM pg_database d CROSS JOIN LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a WHERE datname=current_database() ORDER BY 1,2,3,4"
        )
    ]
    return {"owner": owner, "rights": rights}


def apply_database_acl(admin, target, acl):
    # pg_dump without --create does not include database-level ACLs. Reapply
    # only on our already marked disposable target, never on the source.
    with psycopg.connect(**connection_args(admin), autocommit=True) as conn:
        if (
            not target.startswith("aiced_m1_")
            or not conn.execute(
                "SELECT shobj_description(oid,'pg_database') LIKE 'aiced-m1:%%' FROM pg_database WHERE datname=%s",
                [target],
            ).fetchone()[0]
        ):
            raise ValueError("Unmarked restore target")
        if any(grantor != acl["owner"] for grantor, _, _, _ in acl["rights"]):
            raise ValueError("Non-owner grant chain needs a reviewed restore procedure")
        conn.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                sql.Identifier(target), sql.Identifier(acl["owner"])
            )
        )
        conn.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(target)
            )
        )
        for _, grantee, priv, grantable in acl["rights"]:
            if priv not in ("CREATE", "CONNECT", "TEMPORARY"):
                raise ValueError("Unexpected database privilege")
            conn.execute(
                sql.SQL(
                    "GRANT "
                    + priv
                    + " ON DATABASE {} TO {}"
                    + (" WITH GRANT OPTION" if grantable else "")
                ).format(
                    sql.Identifier(target),
                    (
                        sql.SQL("PUBLIC")
                        if grantee == "PUBLIC"
                        else sql.Identifier(grantee)
                    ),
                )
            )


def snapshot(conn):
    result = {"tables": {}, "catalog": {}, "database_acl": database_acl(conn)}
    for schema in SCHEMAS:
        for (table,) in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname=%s ORDER BY tablename",
            [schema],
        ).fetchall():
            rows = conn.execute(
                sql.SQL(
                    "SELECT to_jsonb(t)::text FROM {}.{} t ORDER BY to_jsonb(t)::text"
                ).format(sql.Identifier(schema), sql.Identifier(table))
            ).fetchall()
            result["tables"][schema + "." + table] = {
                "count": len(rows),
                "sha256": hashlib.sha256(json.dumps(rows).encode()).hexdigest(),
            }
    for name, query in {
        "columns": "SELECT table_schema,table_name,column_name,udt_name,is_nullable,column_default,is_identity,is_generated FROM information_schema.columns WHERE table_schema=ANY(%s) ORDER BY 1,2,ordinal_position",
        "constraints": "SELECT n.nspname,c.relname,k.conname,pg_get_constraintdef(k.oid),k.convalidated FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY(%s) ORDER BY 1,2,3",
        "indexes": "SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes WHERE schemaname=ANY(%s) ORDER BY 1,2,3",
        "triggers": "SELECT n.nspname,c.relname,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY(%s) AND NOT t.tgisinternal ORDER BY 1,2,3",
        "functions": "SELECT n.nspname,p.proname,pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=ANY(%s) AND p.prokind='f' ORDER BY 1,2,pg_get_function_identity_arguments(p.oid)",
        "function_privileges": "SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),pg_get_userbyid(p.proowner),pg_get_userbyid(a.grantor),CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE n.nspname=ANY(%s) ORDER BY 1,2,3,4,5,6,7,8",
        "default_privileges": "SELECT pg_get_userbyid(d.defaclrole),coalesce(n.nspname,''),d.defaclobjtype,pg_get_userbyid(a.grantor),CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace CROSS JOIN LATERAL aclexplode(d.defaclacl) a WHERE d.defaclrole IN (SELECT nspowner FROM pg_namespace WHERE nspname=ANY(%s)) ORDER BY 1,2,3,4,5,6,7",
        "owners": "SELECT n.nspname,c.relname,pg_get_userbyid(c.relowner) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY(%s) AND c.relkind IN ('r','S') ORDER BY 1,2",
        "table_privileges": "SELECT n.nspname,c.relname,pg_get_userbyid(a.grantor),CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault(CASE WHEN c.relkind='S' THEN 'S'::\"char\" ELSE 'r'::\"char\" END,c.relowner))) a WHERE n.nspname=ANY(%s) AND c.relkind IN ('r','S') ORDER BY 1,2,3,4,5,6",
        "column_privileges": "SELECT n.nspname,c.relname,v.attname,pg_get_userbyid(a.grantor),CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable FROM pg_attribute v JOIN pg_class c ON c.oid=v.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(v.attacl) a WHERE n.nspname=ANY(%s) AND NOT v.attisdropped ORDER BY 1,2,3,4,5,6,7",
        "schema_privileges": "SELECT n.nspname,pg_get_userbyid(n.nspowner),pg_get_userbyid(a.grantor),CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable FROM pg_namespace n CROSS JOIN LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a WHERE n.nspname=ANY(%s) ORDER BY 1,2,3,4,5,6",
    }.items():
        result["catalog"][name] = [
            list(r) for r in conn.execute(query, [SCHEMAS]).fetchall()
        ]
    for row in result["catalog"]["constraints"]:
        row[3] = canonical_constraint(row[3])
    result["sequences"] = {}
    for schema, name in conn.execute(
        "SELECT schemaname,sequencename FROM pg_sequences WHERE schemaname=ANY(%s) ORDER BY 1,2",
        [SCHEMAS],
    ).fetchall():
        result["sequences"][schema + "." + name] = list(
            conn.execute(
                sql.SQL("SELECT last_value,is_called FROM {}.{}").format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            ).fetchone()
        )
    return result


def backup_restore(env, admin, directory, label, verify_restore=None):
    run = uuid.uuid4().hex
    target = f"aiced_m1_{run}_restore"
    scratchenv = {**env, "POSTGRES_DB": target, "AICED_REHEARSAL_RUN": run}
    scratch = ScratchDatabases(scratchenv, env["POSTGRES_DB"])
    backup = directory / (label + ".dump")
    pg = [
        "--host",
        admin["POSTGRES_HOST"],
        "--port",
        str(admin["POSTGRES_PORT"]),
        "--username",
        admin["POSTGRES_USER"],
    ]
    child = {**os.environ, **admin, "PGPASSWORD": admin["POSTGRES_PASSWORD"]}

    def execute(name, args):
        with (directory / (label + "-" + name + ".log")).open("wb") as log:
            subprocess.run(args, env=child, stdout=log, stderr=log, check=True)

    try:
        scratch.create(target)
        with psycopg.connect(**connection_args(admin)) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            exported = conn.execute("SELECT pg_export_snapshot()").fetchone()[0]
            before = snapshot(conn)
            execute(
                "dump",
                [
                    pg_binary("pg_dump"),
                    *pg,
                    "--snapshot",
                    exported,
                    "--format=custom",
                    "--file",
                    str(backup),
                    "--dbname",
                    env["POSTGRES_DB"],
                ],
            )
        execute(
            "restore",
            [
                pg_binary("pg_restore"),
                *pg,
                "--exit-on-error",
                "--dbname",
                target,
                str(backup),
            ],
        )
        apply_database_acl(admin, target, before["database_acl"])
        with psycopg.connect(
            **connection_args({**admin, "POSTGRES_DB": target})
        ) as conn:
            require_equal(
                before,
                snapshot(conn),
                "S5 complete restored data/schema/ACL/sequence parity",
            )
        if verify_restore is not None:
            verify_restore({**admin, "POSTGRES_DB": target})
        result = {
            "restored_process_verified": verify_restore is not None,
            "backup": str(backup),
            "sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
            "restoration_verified": True,
            "tables": len(before["tables"]),
        }
        (directory / (label + "-verification.json")).write_text(
            json.dumps(result, indent=2)
        )
        return result
    finally:
        for name in list(scratch.created):
            scratch.drop(name)
