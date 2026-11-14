"""Offline Commercial transfer. Only marked restored databases until cutover approval.

Never run against the application DB from this module. Exact references and
journals are retained; conflicts abort. No deletion/reset of application tables.
"""

import secrets
from psycopg import sql
from s3_database import guard

OWN = "aiced_commercial"
GATE = 591445740000007
BARRIER = 4711239301896721
SCOPE = 591445740000006


def provision(conn, env, verify=guard):
    verify(conn, env)
    run = env["AICED_REHEARSAL_RUN"]
    spec = {
        "roles": {
            k: f"s6_{run}_{v}"
            for k, v in [
                ("owner", "o"),
                ("migrator", "m"),
                ("runtime", "r"),
                ("archive", "a"),
            ]
        },
        "passwords": {k: secrets.token_urlsafe(48) for k in ["migrator", "runtime"]},
    }
    with conn.transaction():
        for kind, role in spec["roles"].items():
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
                ).format(sql.Identifier(role), login)
            )
        conn.execute(
            sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(spec["roles"]["owner"]),
                sql.Identifier(spec["roles"]["migrator"]),
            )
        )
        conn.execute(
            sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                sql.Identifier(OWN), sql.Identifier(spec["roles"]["owner"])
            )
        )
        for kind in ["migrator", "runtime"]:
            conn.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(env["POSTGRES_DB"]),
                    sql.Identifier(spec["roles"][kind]),
                )
            )
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(OWN), sql.Identifier(spec["roles"]["runtime"])
            )
        )
    return spec


def grants(conn, spec):
    role = sql.Identifier(spec["roles"]["runtime"])
    with conn.transaction():
        conn.execute(
            sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA aiced_commercial FROM PUBLIC")
        )
        conn.execute(
            "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA aiced_commercial FROM PUBLIC"
        )
        for table in [
            "commercial_store_journal",
            "commercial_store_internalnonce",
            "commercial_store_partyref",
        ]:
            conn.execute(
                sql.SQL("GRANT SELECT,INSERT ON aiced_commercial.{} TO {}").format(
                    sql.Identifier(table), role
                )
            )
        for table in [
            "commercial_store_actorref",
            "clients_opportunity",
            "commercial_store_outbox",
        ]:
            conn.execute(
                sql.SQL(
                    "GRANT SELECT,INSERT,UPDATE ON aiced_commercial.{} TO {}"
                ).format(sql.Identifier(table), role)
            )
        for table in ["commercial_store_runtimestate", "django_migrations"]:
            conn.execute(
                sql.SQL("GRANT SELECT ON aiced_commercial.{} TO {}").format(
                    sql.Identifier(table), role
                )
            )


def freeze(conn):
    with conn.transaction():
        # Must hold through the entire offline transfer, normally no live listeners.
        conn.execute("SELECT pg_advisory_xact_lock(%s)", [GATE])
        conn.execute(
            "UPDATE aiced_commercial.commercial_store_runtimestate SET mode='frozen' WHERE id=1"
        )


def copy(
    conn,
    source,
    target,
    table,
    columns,
    target_table=None,
    where="TRUE",
    immutable=False,
):
    cols = sql.SQL(",").join(map(sql.Identifier, columns))
    target_table = target_table or table
    source_rel = sql.Identifier(source, table)
    target_rel = sql.Identifier(target, target_table)
    # Both source and target are trusted offline constants. Validate immutable collisions.
    if immutable:
        query = sql.SQL(
            "SELECT 1 FROM {} s JOIN {} t ON s.{}=t.{} WHERE ({}) AND ROW({}) IS DISTINCT FROM ROW({}) LIMIT 1"
        ).format(
            source_rel,
            target_rel,
            sql.Identifier(columns[0]),
            sql.Identifier(columns[0]),
            sql.SQL(where),
            sql.SQL(",").join(
                sql.SQL("s.{}").format(sql.Identifier(c)) for c in columns
            ),
            sql.SQL(",").join(
                sql.SQL("t.{}").format(sql.Identifier(c)) for c in columns
            ),
        )
        if conn.execute(query).fetchone():
            raise RuntimeError("Immutable journal collision")
    updates = sql.SQL(",").join(
        sql.SQL("{}=EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c))
        for c in columns[1:]
    )
    conflict = (
        sql.SQL("DO NOTHING")
        if immutable
        else sql.SQL("DO UPDATE SET {}").format(updates)
    )
    conn.execute(
        sql.SQL(
            "INSERT INTO {} ({}) SELECT {} FROM {} s WHERE {} ON CONFLICT ({}) {}"
        ).format(
            target_rel,
            cols,
            cols,
            source_rel,
            sql.SQL(where),
            sql.Identifier(columns[0]),
            conflict,
        )
    )


def transfer(conn, direction):
    if direction not in ("forward", "reverse"):
        raise ValueError("direction")
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", [GATE])
        conn.execute("SELECT pg_advisory_xact_lock(%s)", [BARRIER])
        conn.execute("SELECT pg_advisory_xact_lock(%s)", [SCOPE])
        conn.execute("SET LOCAL lock_timeout='10s'")
        conn.execute("LOCK TABLE public.clients_opportunity IN ACCESS EXCLUSIVE MODE")
        mode = conn.execute(
            "SELECT mode FROM aiced_commercial.commercial_store_runtimestate WHERE id=1"
        ).fetchone()
        if mode != ("frozen",):
            raise ValueError("Freeze before transfer")
        columns = [
            "id",
            "title",
            "notes",
            "amount",
            "currency",
            "status",
            "due_date",
            "version",
            "updated_at",
            "author_id",
            "party_id",
        ]
        journal = [
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
        if direction == "forward":
            if conn.execute(
                "SELECT 1 FROM public.clients_opportunity o LEFT JOIN public.clients_party p ON p.id=o.party_id LEFT JOIN public.iam_consumer_actorref a ON a.id=o.author_id WHERE p.id IS NULL OR a.id IS NULL LIMIT 1"
            ).fetchone():
                raise ValueError("Dangling legacy opportunity references")
            if conn.execute(
                "SELECT 1 FROM public.clients_party p JOIN aiced_commercial.commercial_store_partyref r ON r.id=p.id WHERE r.organization_id<>p.organization_id LIMIT 1"
            ).fetchone():
                raise ValueError(
                    "Party organization changed; reviewed reconciliation required"
                )
            conn.execute(
                "INSERT INTO aiced_commercial.commercial_store_partyref(id,organization_id) SELECT DISTINCT p.id,p.organization_id FROM public.clients_party p JOIN public.clients_opportunity o ON o.party_id=p.id ON CONFLICT DO NOTHING"
            )
            copy(
                conn,
                "public",
                OWN,
                "iam_consumer_actorref",
                ["id", "username"],
                "commercial_store_actorref",
                where="id IN (SELECT author_id FROM public.clients_opportunity)",
            )
            copy(conn, "public", OWN, "clients_opportunity", columns)
            copy(
                conn,
                "public",
                OWN,
                "audit_auditevent",
                journal,
                "commercial_store_journal",
                where="s.action='clients.opportunities_saved'",
                immutable=True,
            )
            copy(
                conn,
                "public",
                OWN,
                "audit_auditoutbox",
                ["event_id", "created_at", "attempts", "delivered_at"],
                "commercial_store_outbox",
                where="event_id IN (SELECT id FROM aiced_commercial.commercial_store_journal)",
            )
        else:
            copy(
                conn,
                OWN,
                "public",
                "commercial_store_actorref",
                ["id", "username"],
                "iam_consumer_actorref",
            )
            if conn.execute(
                "SELECT 1 FROM aiced_commercial.commercial_store_partyref r LEFT JOIN public.clients_party p ON p.id=r.id WHERE p.id IS NULL OR p.organization_id<>r.organization_id LIMIT 1"
            ).fetchone():
                raise ValueError("Client reference is missing or changed")
            copy(conn, OWN, "public", "clients_opportunity", columns)
            copy(
                conn,
                OWN,
                "public",
                "commercial_store_journal",
                journal,
                "audit_auditevent",
                immutable=True,
            )
            # Legacy outbox requires producer. No business journal is overwritten.
            conn.execute(
                "INSERT INTO public.audit_auditoutbox(event_id,producer,created_at,attempts,delivered_at) SELECT event_id,'commercial',created_at,attempts,delivered_at FROM aiced_commercial.commercial_store_outbox ON CONFLICT(event_id) DO UPDATE SET attempts=EXCLUDED.attempts,delivered_at=EXCLUDED.delivered_at"
            )
        conn.execute(
            "INSERT INTO public.iam_consumer_commercialjournalref(event_id) SELECT id FROM aiced_commercial.commercial_store_journal ON CONFLICT DO NOTHING"
        )
        # Verify full opportunity payload equality including original UUID/Decimal/timestamp.
        left = conn.execute(
            "SELECT to_jsonb(o)::text FROM public.clients_opportunity o ORDER BY id"
        ).fetchall()
        right = conn.execute(
            "SELECT to_jsonb(o)::text FROM aiced_commercial.clients_opportunity o ORDER BY id"
        ).fetchall()
        if left != right:
            raise ValueError("Opportunity transfer parity failed")


def activate(conn, mode):
    if mode not in ("service", "legacy"):
        raise ValueError("mode")
    conn.execute(
        "UPDATE aiced_commercial.commercial_store_runtimestate SET mode=%s WHERE id=1",
        [mode],
    )


def fence(conn, spec, consumer_role, forward):
    # Drain deferred FK events before ownership DDL, retaining all validation.
    conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    if "legacy_owner" not in spec:
        spec["legacy_owner"] = conn.execute(
            "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='public.clients_opportunity'::regclass"
        ).fetchone()[0]
        spec["legacy_acl"] = conn.execute(
            "SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable FROM pg_class c CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid='public.clients_opportunity'::regclass"
        ).fetchall()
    with conn.transaction():
        if forward:
            conn.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    sql.Identifier(spec["roles"]["archive"])
                )
            )
            conn.execute(
                sql.SQL(
                    "GRANT SELECT ON public.clients_party,public.iam_consumer_actorref TO {}"
                ).format(sql.Identifier(spec["roles"]["archive"]))
            )
        owner = spec["roles"]["archive"] if forward else spec["legacy_owner"]
        conn.execute(
            sql.SQL("ALTER TABLE public.clients_opportunity OWNER TO {}").format(
                sql.Identifier(owner)
            )
        )
        grantees = {row[0] for row in spec["legacy_acl"]} | {
            consumer_role,
            spec["legacy_owner"],
            "PUBLIC",
        }
        for role in grantees:
            conn.execute(
                sql.SQL("REVOKE ALL ON public.clients_opportunity FROM {}").format(
                    sql.SQL("PUBLIC") if role == "PUBLIC" else sql.Identifier(role)
                )
            )
        if not forward:
            for role, priv, grantable in spec["legacy_acl"]:
                if priv not in {
                    "SELECT",
                    "INSERT",
                    "UPDATE",
                    "DELETE",
                    "TRUNCATE",
                    "REFERENCES",
                    "TRIGGER",
                    "MAINTAIN",
                }:
                    raise ValueError("Unexpected ACL")
                conn.execute(
                    sql.SQL(
                        "GRANT "
                        + priv
                        + " ON public.clients_opportunity TO {}"
                        + (" WITH GRANT OPTION" if grantable else "")
                    ).format(
                        sql.SQL("PUBLIC") if role == "PUBLIC" else sql.Identifier(role)
                    )
                )
