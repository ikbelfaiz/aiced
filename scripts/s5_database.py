"""Offline S5 ownership operations: guarded restored rehearsal only."""

import hashlib, json, secrets
from psycopg import sql
from s3_database import guard

IAM = "aiced_iam"
GATE = 591445740000003
BARRIER = 4711239301896721
BASE = [
    "django_content_type",
    "auth_group",
    "auth_permission",
    "auth_group_permissions",
    "identity_capability",
    "identity_user",
    "identity_user_groups",
    "identity_user_user_permissions",
    "identity_organization",
    "identity_membership",
    "identity_role",
    "identity_role_permissions",
    "identity_roleassignment",
    "identity_loginbucket",
    "identity_internalnonce",
    "django_session",
]
CANONICAL_LINKS = [
    "auth_group_permissions",
    "identity_user_groups",
    "identity_user_user_permissions",
    "identity_role_permissions",
]
IMMUTABLE = ["audit_auditevent", "audit_auditreceipt"]
IAM_PREFIX = "(action LIKE 'users.%%' OR action LIKE 'permissions.%%' OR action LIKE 'membership.%%' OR action LIKE 'login.%%' OR action LIKE 'logout.%%')"
MAP = {
    "identity_user": "iam_consumer_actorref",
    "identity_organization": "iam_consumer_organizationref",
    "identity_membership": "iam_consumer_membershipref",
}


def provision(conn, env, verify=guard):
    verify(conn, env)
    run = env["AICED_REHEARSAL_RUN"]
    spec = {
        "roles": {
            k: f"s5_{run}_{v}"
            for k, v in [
                ("owner", "o"),
                ("migrator", "m"),
                ("runtime", "r"),
                ("consumer", "c"),
                ("archive", "a"),
            ]
        },
        "passwords": {
            k: secrets.token_urlsafe(48) for k in ["migrator", "runtime", "consumer"]
        },
    }
    with conn.transaction():
        for kind, name in spec["roles"].items():
            login = (
                sql.SQL("LOGIN PASSWORD {}").format(
                    sql.Literal(spec["passwords"][kind])
                )
                if kind in spec["passwords"]
                else sql.SQL("NOLOGIN")
            )
            conn.execute(
                sql.SQL(
                    "CREATE ROLE {} {} NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                ).format(sql.Identifier(name), login)
            )
            conn.execute(
                sql.SQL("COMMENT ON ROLE {} IS {}").format(
                    sql.Identifier(name), sql.Literal("aiced-s5:" + run)
                )
            )
            schema = IAM if kind != "consumer" else "public"
            conn.execute(
                sql.SQL(
                    "ALTER ROLE {} IN DATABASE {} SET search_path TO {},pg_catalog"
                ).format(
                    sql.Identifier(name),
                    sql.Identifier(env["POSTGRES_DB"]),
                    sql.Identifier(schema),
                )
            )
        owner = sql.Identifier(spec["roles"]["owner"])
        runtime = sql.Identifier(spec["roles"]["runtime"])
        consumer = sql.Identifier(spec["roles"]["consumer"])
        conn.execute(
            sql.SQL("GRANT {} TO {}").format(
                owner, sql.Identifier(spec["roles"]["migrator"])
            )
        )
        conn.execute(sql.SQL("CREATE SCHEMA aiced_iam AUTHORIZATION {}").format(owner))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA aiced_iam TO {}").format(runtime))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(consumer))
        # PostgreSQL referential-integrity triggers execute as relation owner. The
        # NOLOGIN archive owner needs schema USAGE to check retained historical FKs.
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                sql.Identifier(spec["roles"]["archive"])
            )
        )
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


def grants(conn, spec):
    with conn.transaction():
        for (table,) in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='aiced_iam'"
        ).fetchall():
            perms = (
                "SELECT"
                if table in ("django_migrations", "iam_control_runtimestate")
                else (
                    "SELECT,INSERT"
                    if table in IMMUTABLE
                    else (
                        "SELECT,INSERT,UPDATE"
                        if table
                        not in (
                            "identity_internalnonce",
                            "django_session",
                            "identity_loginbucket",
                            "identity_role_permissions",
                        )
                        else "SELECT,INSERT,UPDATE,DELETE"
                    )
                )
            )
            conn.execute(
                sql.SQL("GRANT " + perms + " ON aiced_iam.{} TO {}").format(
                    sql.Identifier(table), sql.Identifier(spec["roles"]["runtime"])
                )
            )
        conn.execute(
            sql.SQL(
                "GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA aiced_iam TO {}"
            ).format(sql.Identifier(spec["roles"]["runtime"]))
        )
        for (table,) in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ).fetchall():
            if table.startswith(("identity_", "auth_")) or table in [
                "django_session",
                "django_content_type",
            ]:
                continue
            if (table.startswith('ingestion_') and table != 'ingestion_runtimestate') or table == 'audit_auditreceipt':
                # Retired Integration data and central receipt archives are not
                # needed by the business runtime. Only its cutover control is.
                conn.execute(sql.SQL('REVOKE ALL ON public.{} FROM {}').format(sql.Identifier(table),sql.Identifier(spec['roles']['consumer'])))
                continue
            perms = (
                "SELECT"
                if table.startswith("ingestion_") or table == "django_migrations"
                else (
                    "SELECT,INSERT"
                    if table in IMMUTABLE
                    else (
                        "SELECT,INSERT,UPDATE"
                        if table.startswith("audit_")
                        else "SELECT,INSERT,UPDATE,DELETE"
                    )
                )
            )
            conn.execute(
                sql.SQL("GRANT " + perms + " ON public.{} TO {}").format(
                    sql.Identifier(table), sql.Identifier(spec["roles"]["consumer"])
                )
            )


def freeze(conn):
    # Every extracted writer uses the same DB-scoped revocation barrier; fence
    # drain is bounded and no business or integration transaction crosses this copy.
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout='10000ms'")
        conn.execute("SELECT pg_advisory_xact_lock(%s)", [GATE])
        conn.execute("SELECT pg_advisory_xact_lock(%s)", [BARRIER])
        conn.execute(
            "UPDATE aiced_iam.iam_control_runtimestate SET mode='frozen' WHERE id=1"
        )


def activate(conn, mode):
    if mode not in ("service", "legacy"):
        raise ValueError("Invalid owner")
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", [GATE])
        conn.execute(
            "UPDATE aiced_iam.iam_control_runtimestate SET mode=%s WHERE id=1", [mode]
        )


def columns(conn, schema, table):
    return [
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
            [schema, table],
        )
    ]


def refs(conn):
    with conn.transaction():
        conn.execute(
            "INSERT INTO public.iam_consumer_actorref SELECT id,username FROM public.identity_user ON CONFLICT(id) DO UPDATE SET username=excluded.username"
        )
        conn.execute(
            "INSERT INTO public.iam_consumer_organizationref SELECT id,name,is_active FROM public.identity_organization ON CONFLICT(id) DO UPDATE SET name=excluded.name,is_active=excluded.is_active"
        )
        conn.execute(
            "INSERT INTO public.iam_consumer_membershipref SELECT id,user_id,organization_id FROM public.identity_membership ON CONFLICT(id) DO NOTHING"
        )
        # Explicit equality prevents treating UUID reuse or cross-org memberships as valid.
        if conn.execute(
            "SELECT count(*) FROM public.iam_consumer_membershipref r JOIN public.identity_membership m USING(id) WHERE r.user_id<>m.user_id OR r.organization_id<>m.organization_id"
        ).fetchone()[0]:
            raise ValueError("Reference identity conflict")


def transfer(conn, direction):
    if direction not in ("forward", "reverse"):
        raise ValueError("Unknown direction")
    source, target = ("public", IAM) if direction == "forward" else (IAM, "public")
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", [GATE])
        conn.execute("SELECT pg_advisory_xact_lock(%s)", [BARRIER])
        if conn.execute(
            "SELECT mode FROM aiced_iam.iam_control_runtimestate WHERE id=1"
        ).fetchone() != ("frozen",):
            raise ValueError("IAM must be frozen")
        if not conn.execute(
            "SELECT rolsuper FROM pg_roles WHERE rolname=current_user"
        ).fetchone()[0]:
            raise ValueError("Offline administrator required")
        conn.execute("SET CONSTRAINTS ALL DEFERRED")
        # Canonical sessions must replace the inactive store, including deletions,
        # otherwise a revoked session could be resurrected on rollback.
        for table in [
            "django_session",
            "identity_internalnonce",
            "identity_loginbucket",
            *CANONICAL_LINKS,
        ]:
            conn.execute(
                sql.SQL("DELETE FROM {}.{}").format(
                    sql.Identifier(target), sql.Identifier(table)
                )
            )
        for table in [
            "identity_user",
            "identity_organization",
            "identity_membership",
            "identity_role",
            "identity_roleassignment",
            "identity_capability",
        ]:
            pk = "code" if table == "identity_capability" else "id"
            extra = conn.execute(
                sql.SQL(
                    "SELECT count(*) FROM ((SELECT {} FROM {}.{}) EXCEPT (SELECT {} FROM {}.{})) d"
                ).format(
                    sql.Identifier(pk),
                    sql.Identifier(target),
                    sql.Identifier(table),
                    sql.Identifier(pk),
                    sql.Identifier(source),
                    sql.Identifier(table),
                )
            ).fetchone()[0]
            if extra:
                raise ValueError(
                    "Canonical identity disappeared; reviewed reconciliation required: "
                    + table
                )
        for table in BASE:
            cols = columns(conn, source, table)
            names = sql.SQL(",").join(map(sql.Identifier, cols))
            pk = [
                r[0]
                for r in conn.execute(
                    "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey) WHERE i.indrelid=to_regclass(%s) AND i.indisprimary ORDER BY a.attnum",
                    [source + "." + table],
                )
            ]
            conflict = sql.SQL(",").join(map(sql.Identifier, pk))
            updates = sql.SQL(",").join(
                sql.SQL("{}=excluded.{}").format(sql.Identifier(c), sql.Identifier(c))
                for c in cols
                if c not in pk
            )
            suffix = (
                sql.SQL("DO UPDATE SET {}").format(updates)
                if updates.as_string(conn)
                else sql.SQL("DO NOTHING")
            )
            conn.execute(
                sql.SQL(
                    "INSERT INTO {}.{} ({}) SELECT {} FROM {}.{} ON CONFLICT ({}) {}"
                ).format(
                    sql.Identifier(target),
                    sql.Identifier(table),
                    names,
                    names,
                    sql.Identifier(source),
                    sql.Identifier(table),
                    conflict,
                    suffix,
                )
            )
            # Exact canonical data parity. No implicit date/password/Decimal conversions.
            if conn.execute(
                sql.SQL(
                    "SELECT count(*) FROM ((SELECT {} FROM {}.{}) EXCEPT (SELECT {} FROM {}.{})) d"
                ).format(
                    names,
                    sql.Identifier(source),
                    sql.Identifier(table),
                    names,
                    sql.Identifier(target),
                    sql.Identifier(table),
                )
            ).fetchone()[0]:
                raise ValueError("IAM transfer mismatch " + table)
        if direction == "reverse":
            # IAM-only users may never have called Client/CRM. Validate and
            # materialize their stable references BEFORE copying their audit.
            refs(conn)
        condition = (
            sql.SQL(IAM_PREFIX.replace("%%", "%"))
            if direction == "forward"
            else sql.SQL("TRUE")
        )
        eventcols = columns(conn, source, "audit_auditevent")
        names = sql.SQL(",").join(map(sql.Identifier, eventcols))
        # Validate immutable collisions before inserting, never update audit payloads.
        mismatch = conn.execute(
            sql.SQL(
                "SELECT count(*) FROM {}.audit_auditevent s JOIN {}.audit_auditevent t USING(id) WHERE ({}) AND to_jsonb(s)<>to_jsonb(t)"
            ).format(
                sql.Identifier(source),
                sql.Identifier(target),
                sql.SQL(condition.as_string(conn).replace("action", "s.action")),
            )
        ).fetchone()[0]
        if mismatch:
            raise ValueError("Immutable journal conflict")
        conn.execute(
            sql.SQL(
                "INSERT INTO {}.audit_auditevent ({}) SELECT {} FROM {}.audit_auditevent WHERE {} ON CONFLICT(id) DO NOTHING"
            ).format(
                sql.Identifier(target), names, names, sql.Identifier(source), condition
            )
        )
        conn.execute(
            sql.SQL(
                "INSERT INTO {}.audit_auditoutbox SELECT o.* FROM {}.audit_auditoutbox o JOIN {}.audit_auditevent e ON e.id=o.event_id WHERE {} ON CONFLICT(event_id) DO UPDATE SET attempts=greatest(audit_auditoutbox.attempts,excluded.attempts),delivered_at=coalesce(audit_auditoutbox.delivered_at,excluded.delivered_at)"
            ).format(
                sql.Identifier(target),
                sql.Identifier(source),
                sql.Identifier(source),
                condition,
            )
        )
        # Receipts are immutable and producer/event unique, preserve retries exactly.
        if conn.execute(
            sql.SQL(
                "SELECT count(*) FROM {}.audit_auditreceipt s JOIN {}.audit_auditreceipt t ON s.producer=t.producer AND s.event_id=t.event_id WHERE s.digest<>t.digest OR s.payload<>t.payload"
            ).format(sql.Identifier(source), sql.Identifier(target))
        ).fetchone()[0]:
            raise ValueError("Receipt conflict")
        conn.execute(
            sql.SQL(
                "INSERT INTO {}.audit_auditreceipt SELECT * FROM {}.audit_auditreceipt ON CONFLICT(producer,event_id) DO NOTHING"
            ).format(sql.Identifier(target), sql.Identifier(source))
        )
        conn.execute(
            "INSERT INTO public.iam_consumer_iamjournalref SELECT id FROM aiced_iam.audit_auditevent ON CONFLICT DO NOTHING"
        )
        for table in BASE:
            for seq, col in conn.execute(
                "SELECT pg_get_serial_sequence(%s,column_name),column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s",
                [target + "." + table, target, table],
            ).fetchall():
                if seq:
                    source_seq = conn.execute(
                        "SELECT pg_get_serial_sequence(%s,%s)",
                        [source + "." + table, col],
                    ).fetchone()[0]
                    source_value, source_called = conn.execute(
                        sql.SQL("SELECT last_value,is_called FROM {}").format(
                            sql.Identifier(*source_seq.split("."))
                        )
                    ).fetchone()
                    target_value, target_called = conn.execute(
                        sql.SQL("SELECT last_value,is_called FROM {}").format(
                            sql.Identifier(*seq.split("."))
                        )
                    ).fetchone()
                    max_value = conn.execute(
                        sql.SQL("SELECT coalesce(max({}),0) FROM {}.{}").format(
                            sql.Identifier(col),
                            sql.Identifier(target),
                            sql.Identifier(table),
                        )
                    ).fetchone()[0]
                    conn.execute(
                        "SELECT setval(%s,%s,%s)",
                        [
                            seq,
                            max(source_value, target_value, max_value, 1),
                            source_called or target_called or max_value > 0,
                        ],
                    )


def retarget(conn, remote=True):
    mapping = MAP if remote else {v: k for k, v in MAP.items()}
    with conn.transaction():
        rows = conn.execute(
            "SELECT c.relname,k.conname,t.relname,pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_class t ON t.oid=k.confrelid WHERE k.contype='f' AND n.nspname='public' AND (c.relname LIKE 'clients_%%' OR c.relname='audit_auditevent')"
        ).fetchall()
        for table, name, target, definition in rows:
            if target not in mapping:
                continue
            replacement = definition.replace(
                "REFERENCES " + target + "(",
                "REFERENCES public." + mapping[target] + "(",
            ).replace(
                "REFERENCES public." + target + "(",
                "REFERENCES public." + mapping[target] + "(",
            )
            if replacement == definition:
                raise ValueError("Unrecognized FK definition")
            conn.execute(
                sql.SQL("ALTER TABLE public.{} DROP CONSTRAINT {}").format(
                    sql.Identifier(table), sql.Identifier(name)
                )
            )
            conn.execute(
                sql.SQL("ALTER TABLE public.{} ADD CONSTRAINT {} ").format(
                    sql.Identifier(table), sql.Identifier(name)
                )
                + sql.SQL(replacement)
            )


def fence(conn, spec, legacy_user, remote=True):
    with conn.transaction():
        for table in BASE:
            owner = spec["roles"]["archive"] if remote else legacy_user
            conn.execute(
                sql.SQL("ALTER TABLE public.{} OWNER TO {}").format(
                    sql.Identifier(table), sql.Identifier(owner)
                )
            )
            if remote:
                conn.execute(
                    sql.SQL("REVOKE ALL ON public.{} FROM {}").format(
                        sql.Identifier(table), sql.Identifier(legacy_user)
                    )
                )
        conn.execute(
            sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA aiced_iam FROM {}").format(
                sql.Identifier(spec["roles"]["consumer"])
            )
        )
