"""S3 schema provisioning/copy tools, restricted to marked disposable restores.

Not an unattended production cutover tool. All identifiers are composed with
psycopg.sql. Secrets stay in private files/environment, never CLI or reports.
"""

import secrets
from psycopg import sql
from testing.rehearsal import validate_environment

SCHEMA = "aiced_integration"
TABLES = [
    "ingestion_importpolicy",
    "ingestion_importbatch",
    "ingestion_stagingrow",
    "ingestion_sourcesnapshot",
]


def guard(conn, env):
    name = validate_environment(env)
    if not name.endswith("_restore") or conn.execute(
        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).fetchone() != (name, "aiced-m1:" + env["AICED_REHEARSAL_RUN"]):
        raise ValueError("Only marked disposable restored databases are supported")


def provision(conn, env, verify=guard):
    verify(conn, env)
    run = env["AICED_REHEARSAL_RUN"]
    spec = {
        "schema": SCHEMA,
        "roles": {
            kind: f"s3_{run}_{suffix}"
            for kind, suffix in (("owner", "o"), ("migrator", "m"), ("runtime", "r"))
        },
        "passwords": {
            kind: secrets.token_urlsafe(48) for kind in ("migrator", "runtime")
        },
    }
    with conn.transaction():
        for kind, name in spec["roles"].items():
            login = (
                sql.SQL("NOLOGIN")
                if kind == "owner"
                else sql.SQL("LOGIN PASSWORD {}").format(
                    sql.Literal(spec["passwords"][kind])
                )
            )
            conn.execute(
                sql.SQL(
                    "CREATE ROLE {} {} NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                ).format(sql.Identifier(name), login)
            )
            conn.execute(
                sql.SQL("COMMENT ON ROLE {} IS {}").format(
                    sql.Identifier(name), sql.Literal("aiced-s3:" + run)
                )
            )
            conn.execute(
                sql.SQL(
                    "ALTER ROLE {} IN DATABASE {} SET search_path TO {},pg_catalog"
                ).format(
                    sql.Identifier(name),
                    sql.Identifier(env["POSTGRES_DB"]),
                    sql.Identifier(SCHEMA),
                )
            )
        owner, migrator, runtime = [
            sql.Identifier(spec["roles"][kind])
            for kind in ("owner", "migrator", "runtime")
        ]
        conn.execute(sql.SQL("GRANT {} TO {}").format(owner, migrator))
        conn.execute(
            sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                sql.Identifier(SCHEMA), owner
            )
        )
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(SCHEMA), runtime
            )
        )
        # Public grants cannot be negated by a per-role REVOKE. In the restored
        # scratch only, remove public schema access for PUBLIC. Existing owner
        # retains its own rights. This needs an audited ACL rollout before S4.
        conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        conn.execute(
            sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(env["POSTGRES_DB"])
            )
        )
        conn.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
            ).format(owner)
        )
    return spec


def grant_runtime(conn, spec):
    runtime = sql.Identifier(spec["roles"]["runtime"])
    with conn.transaction():
        conn.execute(
            sql.SQL("GRANT SELECT ON TABLE {}.django_migrations TO {}").format(
                sql.Identifier(SCHEMA), runtime
            )
        )
        conn.execute(
            sql.SQL(
                "GRANT SELECT ON TABLE {}.integration_store_runtimestate TO {}"
            ).format(sql.Identifier(SCHEMA), runtime)
        )
        conn.execute(
            sql.SQL(
                "GRANT SELECT,INSERT,DELETE ON TABLE {}.integration_store_internalnonce TO {}"
            ).format(sql.Identifier(SCHEMA), runtime)
        )
        for table in [
            *TABLES,
            "integration_store_actorref",
            "integration_store_organizationref",
            "integration_store_journal",
            "integration_store_outbox",
        ]:
            conn.execute(
                sql.SQL("GRANT SELECT,INSERT ON TABLE {}.{} TO {}").format(
                    sql.Identifier(SCHEMA), sql.Identifier(table), runtime
                )
            )
        for table, columns in [
            ("ingestion_importpolicy", "approved_by_id,approved_at,revoked_at"),
            ("ingestion_importbatch", "status,published_by_id,published_at,policy_id"),
            ("integration_store_outbox", "attempts,delivered_at"),
        ]:
            conn.execute(
                sql.SQL("GRANT UPDATE ({}) ON TABLE {}.{} TO {}").format(
                    sql.SQL(columns),
                    sql.Identifier(SCHEMA),
                    sql.Identifier(table),
                    runtime,
                )
            )


def copy_restored(conn, env):
    """Offline one-writer rehearsal. Preserve UUIDs/dates/JSON, never model.save()."""
    guard(conn, env)
    with conn.transaction():
        # A successful local FK check isn't a durable remote authorization grant.
        # It validates historical references during the controlled offline copy.
        for table, fields in [
            (TABLES[0], ["created_by_id", "approved_by_id"]),
            (TABLES[1], ["uploaded_by_id", "published_by_id"]),
        ]:
            for field in fields:
                missing = conn.execute(
                    sql.SQL(
                        "SELECT count(*) FROM public.{} t LEFT JOIN public.identity_user u ON t.{}=u.id WHERE t.{} IS NOT NULL AND u.id IS NULL"
                    ).format(
                        sql.Identifier(table),
                        sql.Identifier(field),
                        sql.Identifier(field),
                    )
                ).fetchone()[0]
                if missing:
                    raise ValueError("Unresolvable historical actor reference")
            if conn.execute(
                sql.SQL(
                    "SELECT count(*) FROM public.{} t LEFT JOIN public.identity_organization o ON t.organization_id=o.id WHERE o.id IS NULL"
                ).format(sql.Identifier(table))
            ).fetchone()[0]:
                raise ValueError("Unresolvable historical organization reference")
        conn.execute(
            """INSERT INTO aiced_integration.integration_store_actorref(id)
          SELECT created_by_id FROM public.ingestion_importpolicy UNION SELECT approved_by_id FROM public.ingestion_importpolicy WHERE approved_by_id IS NOT NULL
          UNION SELECT uploaded_by_id FROM public.ingestion_importbatch UNION SELECT published_by_id FROM public.ingestion_importbatch WHERE published_by_id IS NOT NULL"""
        )
        conn.execute(
            """INSERT INTO aiced_integration.integration_store_organizationref(id)
          SELECT organization_id FROM public.ingestion_importpolicy UNION SELECT organization_id FROM public.ingestion_importbatch"""
        )
        for table in TABLES:
            columns = sql.SQL(",").join(
                sql.Identifier(row[0])
                for row in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
                    (table,),
                )
            )
            conn.execute(
                sql.SQL("INSERT INTO {}.{} ({}) SELECT {} FROM public.{}").format(
                    sql.Identifier(SCHEMA),
                    sql.Identifier(table),
                    columns,
                    columns,
                    sql.Identifier(table),
                )
            )
        conn.execute(
            """INSERT INTO aiced_integration.integration_store_journal
          (id,occurred_at,actor_id,organization_id,action,target_id,result,request_id,context)
          SELECT id,occurred_at,actor_id,organization_id,action,target_id,result,request_id,context
          FROM public.audit_auditevent WHERE action LIKE 'imports.%'"""
        )
        conn.execute(
            """INSERT INTO aiced_integration.integration_store_outbox(event_id,created_at,attempts,delivered_at)
          SELECT o.event_id,o.created_at,o.attempts,o.delivered_at FROM public.audit_auditoutbox o
          JOIN aiced_integration.integration_store_journal j ON j.id=o.event_id"""
        )
        # Pre-S2 journal records deliberately do not acquire new delivery tasks.
        if conn.execute(
            """SELECT EXISTS(
          (SELECT id,occurred_at,actor_id,organization_id,action,target_id,result,request_id,context FROM public.audit_auditevent WHERE action LIKE 'imports.%'
           EXCEPT SELECT id,occurred_at,actor_id,organization_id,action,target_id,result,request_id,context FROM aiced_integration.integration_store_journal)
          UNION ALL
          (SELECT id,occurred_at,actor_id,organization_id,action,target_id,result,request_id,context FROM aiced_integration.integration_store_journal
           EXCEPT SELECT id,occurred_at,actor_id,organization_id,action,target_id,result,request_id,context FROM public.audit_auditevent WHERE action LIKE 'imports.%'))"""
        ).fetchone()[0]:
            raise ValueError("Import audit history parity failed")
        for table in TABLES:
            equal = conn.execute(
                sql.SQL(
                    "SELECT NOT EXISTS((SELECT to_jsonb(t) FROM public.{} t EXCEPT SELECT to_jsonb(t) FROM {}.{} t) UNION ALL (SELECT to_jsonb(t) FROM {}.{} t EXCEPT SELECT to_jsonb(t) FROM public.{} t))"
                ).format(
                    sql.Identifier(table),
                    sql.Identifier(SCHEMA),
                    sql.Identifier(table),
                    sql.Identifier(SCHEMA),
                    sql.Identifier(table),
                    sql.Identifier(table),
                )
            ).fetchone()[0]
            if not equal:
                raise ValueError("Exact copy parity failed")


def cleanup_roles(conn, env, spec):
    for kind in (
        "runtime",
        "migrator",
        "owner",
        *(["archive"] if "archive" in spec["roles"] else []),
    ):
        name = spec["roles"][kind]
        marker = conn.execute(
            "SELECT shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname=%s",
            (name,),
        ).fetchone()
        if marker != ("aiced-s3:" + env["AICED_REHEARSAL_RUN"],):
            raise ValueError("Role cleanup marker mismatch")
        conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))
