"""S1 disposable PostgreSQL schema/credential boundary rehearsal, not a cutover.

Only new M1-marked, empty scratch databases are accepted. No command here can
provision, alter ownership of, or revoke privileges on the application database.
"""

import argparse
import json
from pathlib import Path
import secrets
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
    ScratchDatabases,
    connection_args,
    fingerprint,
    require_equal,
)
from testing.rehearsal import validate_environment
from service_architecture.ownership import SCHEMAS


def guard(conn, env):
    expected = validate_environment(env)
    row = conn.execute(
        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    if row != (expected, "aiced-m1:" + env["AICED_REHEARSAL_RUN"]):
        raise ValueError("Scratch database marker mismatch")
    if conn.execute(
        "SELECT 1 FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') LIMIT 1"
    ).fetchone():
        raise ValueError(
            "Provisioning refuses any database containing application tables"
        )


def provision(conn, env):
    """Atomic schema, role and default-ACL installation in an empty scratch DB."""
    guard(conn, env)
    run = env["AICED_REHEARSAL_RUN"]
    result = {}
    with conn.transaction():
        conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        conn.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(env["POSTGRES_DB"])
            )
        )
        for service, schema in SCHEMAS.items():
            prefix = f"ar_{run}_{service}"
            names = {
                "owner": prefix + "_o",
                "migrator": prefix + "_m",
                "runtime": prefix + "_r",
            }
            passwords = {
                kind: secrets.token_urlsafe(48) for kind in ("migrator", "runtime")
            }
            for kind, name in names.items():
                login = (
                    sql.SQL("NOLOGIN")
                    if kind == "owner"
                    else sql.SQL("LOGIN PASSWORD {}").format(
                        sql.Literal(passwords[kind])
                    )
                )
                conn.execute(
                    sql.SQL(
                        "CREATE ROLE {} {} NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                    ).format(sql.Identifier(name), login)
                )
                conn.execute(
                    sql.SQL("COMMENT ON ROLE {} IS {}").format(
                        sql.Identifier(name), sql.Literal("aiced-s1:" + run)
                    )
                )
                conn.execute(
                    sql.SQL(
                        "ALTER ROLE {} IN DATABASE {} SET search_path TO {}, pg_catalog"
                    ).format(
                        sql.Identifier(name),
                        sql.Identifier(env["POSTGRES_DB"]),
                        sql.Identifier(schema),
                    )
                )
            owner, migrator, runtime = [
                sql.Identifier(names[k]) for k in ("owner", "migrator", "runtime")
            ]
            conn.execute(sql.SQL("GRANT {} TO {}").format(owner, migrator))
            conn.execute(
                sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                    sql.Identifier(schema), owner
                )
            )
            conn.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(schema), runtime
                )
            )
            conn.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
                    sql.Identifier(env["POSTGRES_DB"]), migrator, runtime
                )
            )
            conn.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
                ).format(owner, sql.Identifier(schema), runtime)
            )
            conn.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT USAGE, SELECT ON SEQUENCES TO {}"
                ).format(owner, sql.Identifier(schema), runtime)
            )
            conn.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
                ).format(owner)
            )
            result[service] = {"schema": schema, "roles": names, "passwords": passwords}
    return result


def denied(conn, statement, expected="42501"):
    try:
        with conn.transaction():
            conn.execute(statement)
            # Every probe rolls back even if access was accidentally allowed.
            raise AssertionError("Unexpectedly allowed a forbidden database operation")
    except psycopg.Error as error:
        if error.sqlstate != expected:
            raise AssertionError(
                f"Expected SQLSTATE {expected}, got {error.sqlstate}"
            ) from error


def verify(env, services):
    checks = []

    def connect(service, kind):
        spec = services[service]
        return psycopg.connect(
            **{
                **connection_args(env),
                "user": spec["roles"][kind],
                "password": spec["passwords"][kind],
            },
            autocommit=True,
        )

    # Real distinct LOGIN connections, not SET ROLE under a superuser session.
    for service, spec in services.items():
        with connect(service, "migrator") as conn:
            denied(
                conn,
                sql.SQL("CREATE TABLE {}.forbidden(id int)").format(
                    sql.Identifier(spec["schema"])
                ),
            )
            conn.execute(
                sql.SQL("SET ROLE {}").format(sql.Identifier(spec["roles"]["owner"]))
            )
            conn.execute(
                "CREATE TABLE boundary_probe(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, label text NOT NULL)"
            )
            conn.execute(
                "CREATE FUNCTION private_probe() RETURNS integer LANGUAGE sql AS 'SELECT 1'"
            )
            conn.execute("RESET ROLE")
            checks.append(service + ":migration-owner-only")
    for service, spec in services.items():
        with connect(service, "runtime") as conn:
            identity = conn.execute("SELECT current_user, current_schema()").fetchone()
            if identity != (spec["roles"]["runtime"], spec["schema"]):
                raise AssertionError(
                    "Connection/search_path crossed a service boundary"
                )
            conn.execute("INSERT INTO boundary_probe(label) VALUES ('SYNTHETIC')")
            if conn.execute("SELECT label FROM boundary_probe").fetchone() != (
                "SYNTHETIC",
            ):
                raise AssertionError("Own-table read failed")
            conn.execute("UPDATE boundary_probe SET label='SYNTHETIC edited'")
            conn.execute("DELETE FROM boundary_probe")
            denied(conn, "CREATE TABLE forbidden(id int)")
            denied(conn, "TRUNCATE boundary_probe")
            denied(conn, "ALTER TABLE boundary_probe ADD COLUMN forbidden int")
            denied(conn, "SELECT private_probe()")
            denied(conn, "CREATE TEMP TABLE forbidden(id int)")
            denied(
                conn,
                sql.SQL("SET ROLE {}").format(sql.Identifier(spec["roles"]["owner"])),
            )
            denied(
                conn,
                sql.SQL("SET ROLE {}").format(
                    sql.Identifier(spec["roles"]["migrator"])
                ),
            )
            denied(conn, "CREATE ROLE aiced_forbidden_probe", expected="42501")
            denied(conn, "CREATE TABLE public.forbidden(id int)")
            for other, foreign in services.items():
                if other == service:
                    continue
                table = sql.SQL("{}.boundary_probe").format(
                    sql.Identifier(foreign["schema"])
                )
                for command in [
                    sql.SQL("SELECT * FROM {}"),
                    sql.SQL("INSERT INTO {}(label) VALUES ('forbidden')"),
                    sql.SQL("UPDATE {} SET label='forbidden'"),
                    sql.SQL("DELETE FROM {}"),
                ]:
                    denied(conn, command.format(table))
                denied(
                    conn,
                    sql.SQL("SET ROLE {}").format(
                        sql.Identifier(foreign["roles"]["owner"])
                    ),
                )
                conn.execute(
                    sql.SQL("SET search_path TO {}, pg_catalog").format(
                        sql.Identifier(foreign["schema"])
                    )
                )
                denied(conn, "SELECT * FROM boundary_probe", expected="42P01")
                conn.execute(
                    sql.SQL("SET search_path TO {}, pg_catalog").format(
                        sql.Identifier(spec["schema"])
                    )
                )
                checks.append(service + "->" + other + ":read-write-role-path-denied")
            checks.append(service + ":runtime-crud-and-ddl-escalation-denials")
        # Migration credentials also cannot become a different service owner.
        with connect(service, "migrator") as conn:
            for other, foreign in services.items():
                if other != service:
                    denied(
                        conn,
                        sql.SQL("SET ROLE {}").format(
                            sql.Identifier(foreign["roles"]["owner"])
                        ),
                    )
                    denied(
                        conn,
                        sql.SQL("SELECT * FROM {}.boundary_probe").format(
                            sql.Identifier(foreign["schema"])
                        ),
                    )
    return checks


def cleanup_roles(env, services):
    # The scratch database must be dropped first, removing only its dependencies.
    run = env["AICED_REHEARSAL_RUN"]
    with psycopg.connect(**connection_args(env, "postgres"), autocommit=True) as conn:
        for spec in services.values():
            for kind in ("runtime", "migrator", "owner"):
                name = spec["roles"][kind]
                row = conn.execute(
                    "SELECT shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname=%s",
                    (name,),
                ).fetchone()
                if row != ("aiced-s1:" + run,):
                    raise ValueError("Refusing cleanup of an unmarked role")
                # DROP ROLE fails if any unexpected external dependency exists.
                conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-synthetic", required=True, action="store_true")
    parser.add_argument(
        "--env-file", type=Path, default=ROOT / ".local/postgres/env.json"
    )
    parser.add_argument(
        "--admin-file", type=Path, default=ROOT / ".local/postgres/credentials.json"
    )
    options = parser.parse_args()
    original = json.loads(options.env_file.read_text())
    # This CLI deliberately supports only the repository's portable local cluster.
    if (
        original["POSTGRES_HOST"] != "127.0.0.1"
        or str(original["POSTGRES_PORT"]) != "55432"
        or original.get("DJANGO_DEBUG") != "1"
    ):
        raise ValueError(
            "Only the portable loopback synthetic development cluster is supported"
        )
    run = uuid.uuid4().hex
    env = {
        **original,
        "AICED_REHEARSAL_RUN": run,
        "POSTGRES_USER": "aiced_owner",
        "POSTGRES_PASSWORD": json.loads(options.admin_file.read_text())["owner"],
        "POSTGRES_DB": f"aiced_m1_{run}_source",
    }
    scratch = ScratchDatabases(env, original["POSTGRES_DB"])
    directory = ROOT / ".local/service-boundaries" / run
    directory.mkdir(parents=True)
    before = fingerprint(original)
    report = {
        "run": run,
        "status": "running",
        "tables_moved": False,
        "independent_services": [],
        "checks": [],
    }
    services = {}
    try:
        scratch.create(env["POSTGRES_DB"])
        with psycopg.connect(**connection_args(env), autocommit=True) as conn:
            services = provision(conn, env)
        report["checks"] = verify(env, services)
        report["status"] = "passed"
    except Exception:
        report["status"] = "failed"
        raise
    finally:
        try:
            require_equal(
                before, fingerprint(original), "Existing database preservation"
            )
            report["existing_database_unchanged"] = True
            for name in list(scratch.created):
                scratch.drop(name)
            if services:
                cleanup_roles(env, services)
            report["scratch_database_and_roles_removed"] = True
        except Exception:
            report["status"] = "failed"
            raise
        finally:
            (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f'S1 schema rehearsal {report["status"]}; {directory / "report.json"}')


if __name__ == "__main__":
    main()
