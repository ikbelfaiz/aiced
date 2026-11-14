"""Offline, frozen-domain transfer in either direction; never a runtime API.

Caller must verify backup/restore before provisioning and must stop old workers.
No immutable row is updated/deleted. Divergence aborts the entire transaction.
"""

from psycopg import sql
from s3_database import TABLES, SCHEMA

LEGACY_GATE = 591445740000001
SERVICE_GATE = 591445740000002
STATES = {"public": "ingestion_runtimestate", SCHEMA: "integration_store_runtimestate"}
MUTABLE = {
    TABLES[0]: ["approved_by_id", "approved_at", "revoked_at"],
    TABLES[1]: ["status", "published_by_id", "published_at", "policy_id"],
}


def fence_legacy(conn, env, spec, active=True):
    """Retire ownership/DML from the old writer, not just its HTTP route."""
    archive = spec["roles"].get("archive")
    if not archive:
        archive = spec["roles"]["owner"][:-2] + "_a"
        spec["roles"]["archive"] = archive
        conn.execute(
            sql.SQL(
                "CREATE ROLE {} NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
            ).format(sql.Identifier(archive))
        )
        conn.execute(
            sql.SQL("COMMENT ON ROLE {} IS {}").format(
                sql.Identifier(archive),
                sql.Literal("aiced-s3:" + env["AICED_REHEARSAL_RUN"]),
            )
        )
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                sql.Identifier(archive)
            )
        )
    role = sql.Identifier(env["POSTGRES_USER"])
    for table in TABLES:
        owner = archive if active else env["POSTGRES_USER"]
        conn.execute(
            sql.SQL("ALTER TABLE {} OWNER TO {}").format(
                ident("public", table), sql.Identifier(owner)
            )
        )
        conn.execute(
            sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(
                ident("public", table), role
            )
        )
        conn.execute(
            sql.SQL("GRANT {} ON TABLE {} TO {}").format(
                sql.SQL("SELECT" if active else "ALL"), ident("public", table), role
            )
        )
    conn.execute(
        sql.SQL("ALTER TABLE public.ingestion_runtimestate OWNER TO {}").format(
            sql.Identifier(archive)
        )
    )
    conn.execute(
        sql.SQL("GRANT SELECT ON public.ingestion_runtimestate TO {}").format(role)
    )


def ident(schema, table):
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(table))


def freeze(conn):
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout='15s'")
        for key in (LEGACY_GATE, SERVICE_GATE):
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
        for schema, table in STATES.items():
            conn.execute(
                sql.SQL(
                    "INSERT INTO {} (id,mode) VALUES(1,'frozen') ON CONFLICT(id) DO UPDATE SET mode='frozen'"
                ).format(ident(schema, table))
            )


def activate(conn, destination):
    if destination not in STATES:
        raise ValueError("Unknown destination")
    with conn.transaction():
        for key in (LEGACY_GATE, SERVICE_GATE):
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
        for schema, table in STATES.items():
            # Both private controls record the same canonical owner. Each
            # runtime admits only its own expected mode. 'frozen' always means
            # maintenance, including for public audit reads during reverse copy.
            phase = "legacy" if destination == "public" else "service"
            conn.execute(
                sql.SQL("UPDATE {} SET mode=%s WHERE id=1").format(
                    ident(schema, table)
                ),
                (phase,),
            )


def frozen(conn):
    for schema, table in STATES.items():
        if conn.execute(
            sql.SQL("SELECT mode FROM {} WHERE id=1").format(ident(schema, table))
        ).fetchone() != ("frozen",):
            raise ValueError("Both import writers must be frozen before transfer")
    if not conn.execute(
        "SELECT rolsuper FROM pg_roles WHERE rolname=current_user"
    ).fetchone()[0]:
        raise ValueError(
            "Offline transfer requires the approved database administrator"
        )


def equal_table(conn, source, destination, table):
    a, b = ident(source, table), ident(destination, table)
    mismatch = conn.execute(
        sql.SQL(
            "SELECT EXISTS((SELECT to_jsonb(t) FROM {} t EXCEPT SELECT to_jsonb(t) FROM {} t) UNION ALL (SELECT to_jsonb(t) FROM {} t EXCEPT SELECT to_jsonb(t) FROM {} t))"
        ).format(a, b, b, a)
    ).fetchone()[0]
    if mismatch:
        raise ValueError("Domain parity mismatch: " + table)


def transfer(conn, source, destination):
    if {source, destination} != {"public", SCHEMA}:
        raise ValueError("Only the existing legacy/owned boundary is supported")
    with conn.transaction():
        frozen(conn)
        # Synchronize with any final in-flight job DML and acquire the gates for
        # the entire copy. Deployment changes take the same lock order.
        for key in (LEGACY_GATE, SERVICE_GATE):
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
        frozen(conn)
        for schema in ("public", SCHEMA):
            for table in TABLES:
                conn.execute(
                    sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(
                        ident(schema, table)
                    )
                )
        if destination == SCHEMA:
            for target, select in [
                (
                    "integration_store_actorref",
                    "SELECT created_by_id id FROM public.ingestion_importpolicy UNION SELECT approved_by_id FROM public.ingestion_importpolicy WHERE approved_by_id IS NOT NULL UNION SELECT uploaded_by_id FROM public.ingestion_importbatch UNION SELECT published_by_id FROM public.ingestion_importbatch WHERE published_by_id IS NOT NULL",
                ),
                (
                    "integration_store_organizationref",
                    "SELECT organization_id id FROM public.ingestion_importpolicy UNION SELECT organization_id FROM public.ingestion_importbatch",
                ),
            ]:
                # Source FKs still validate these historical IAM references.
                conn.execute(
                    sql.SQL("INSERT INTO {} (id) {} ON CONFLICT DO NOTHING").format(
                        ident(SCHEMA, target), sql.SQL(select)
                    )
                )
        for table in TABLES:
            a, b = ident(source, table), ident(destination, table)
            mutable = MUTABLE.get(table, [])
            if mutable:
                sub = sql.SQL(" - ").join(sql.Literal(field) for field in mutable)
                difference = sql.SQL("to_jsonb(s) - {} <> to_jsonb(d) - {}").format(
                    sub, sub
                )
            else:
                difference = sql.SQL("to_jsonb(s)<>to_jsonb(d)")
            if conn.execute(
                sql.SQL(
                    "SELECT EXISTS(SELECT 1 FROM {} s JOIN {} d USING(id) WHERE {})"
                ).format(a, b, difference)
            ).fetchone()[0]:
                raise ValueError("Immutable transfer conflict: " + table)
            columns = sql.SQL(",").join(
                sql.Identifier(row[0])
                for row in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
                    (destination, table),
                )
            )
            sourcecols = sql.SQL(",").join(
                sql.SQL("s.{}").format(sql.Identifier(row[0]))
                for row in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
                    (destination, table),
                )
            )
            conn.execute(
                sql.SQL(
                    "INSERT INTO {} ({}) SELECT {} FROM {} s WHERE NOT EXISTS(SELECT 1 FROM {} d WHERE d.id=s.id)"
                ).format(b, columns, sourcecols, a, b)
            )
            if mutable:
                sets = sql.SQL(",").join(
                    sql.SQL("{}=s.{}").format(
                        sql.Identifier(field), sql.Identifier(field)
                    )
                    for field in mutable
                )
                conn.execute(
                    sql.SQL("UPDATE {} d SET {} FROM {} s WHERE d.id=s.id").format(
                        b, sets, a
                    )
                )
            equal_table(conn, source, destination, table)
        # Preserve full immutable journal payloads, attribution and delivery state.
        fields = [
            "id",
            "occurred_at",
            "actor_id",
            "organization_id",
            "action",
            "target_id",
            "result",
            "request_id",
            "context",
        ]
        cols = sql.SQL(",").join(sql.Identifier(f) for f in fields)
        if source == "public":
            sourceevents = sql.SQL(
                "(SELECT e.{} FROM public.audit_auditevent e WHERE e.action LIKE 'imports.%' OR EXISTS(SELECT 1 FROM public.audit_auditoutbox o WHERE o.event_id=e.id AND o.producer='integration'))"
            ).format(sql.SQL(",e.").join(sql.Identifier(f) for f in fields))
            target = ident(SCHEMA, "integration_store_journal")
        else:
            sourceevents = ident(SCHEMA, "integration_store_journal")
            target = ident("public", "audit_auditevent")
        # Use an explicit projection to ignore any future technical journal columns.
        src = sql.SQL("(SELECT {} FROM {} x)").format(cols, sourceevents)
        if conn.execute(
            sql.SQL(
                "SELECT EXISTS(SELECT 1 FROM {} s JOIN {} d ON d.id=s.id WHERE to_jsonb(s)<>(SELECT to_jsonb(y) FROM (SELECT {} FROM {} z WHERE z.id=d.id) y))"
            ).format(src, target, cols, target)
        ).fetchone()[0]:
            raise ValueError("Immutable audit conflict")
        conn.execute(
            sql.SQL(
                "INSERT INTO {} ({}) SELECT s.* FROM {} s WHERE NOT EXISTS(SELECT 1 FROM {} d WHERE d.id=s.id)"
            ).format(target, cols, src, target)
        )
        if destination == "public":
            conn.execute(
                """INSERT INTO public.audit_auditoutbox(event_id,producer,created_at,delivered_at,attempts)
              SELECT event_id,'integration',created_at,delivered_at,attempts FROM aiced_integration.integration_store_outbox
              ON CONFLICT(event_id) DO UPDATE SET
              delivered_at=coalesce(audit_auditoutbox.delivered_at,excluded.delivered_at),
              attempts=greatest(audit_auditoutbox.attempts,excluded.attempts)"""
            )
        else:
            conn.execute(
                """INSERT INTO aiced_integration.integration_store_outbox(event_id,created_at,delivered_at,attempts)
              SELECT event_id,created_at,delivered_at,attempts FROM public.audit_auditoutbox o
              WHERE EXISTS(SELECT 1 FROM aiced_integration.integration_store_journal j WHERE j.id=o.event_id)
              ON CONFLICT(event_id) DO UPDATE SET
              delivered_at=coalesce(integration_store_outbox.delivered_at,excluded.delivered_at),
              attempts=greatest(integration_store_outbox.attempts,excluded.attempts)"""
            )
