"""Synthetic HTTP acceptance for the existing local S5 deployment, no printed secrets."""

import argparse, hashlib, json, sys, uuid, secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / ".tools/python"),
    str(ROOT / "backend"),
    str(ROOT / "scripts"),
]
import psycopg
from psycopg import sql
from migration_baseline import connection_args
from s3_rehearsal import Browser
from s5_local import validate, write


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--phase", choices=["stage", "rollback", "final"], required=True)
    args = p.parse_args()
    directory = args.directory.resolve()
    env = json.loads((directory / "s5-legacy-backend-env.json").read_text())
    validate(env)
    admin = {
        **env,
        "POSTGRES_USER": "aiced_owner",
        "POSTGRES_PASSWORD": json.loads(
            (ROOT / ".local/postgres/credentials.json").read_text()
        )["owner"],
    }
    base = "http://127.0.0.1:" + str(
        json.loads((directory / "deployment.json").read_text())["gateway_port"]
    )
    password = (ROOT / ".local/postgres/seed-password").read_text().strip()
    path = directory / "s5-http-verification.json"
    state = json.loads(path.read_text()) if path.exists() else {}

    def hashes(conn, prefix, schema):
        result = {}
        for (table,) in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname=%s AND tablename LIKE %s ORDER BY tablename",
            [schema, prefix],
        ).fetchall():
            data = conn.execute(
                sql.SQL(
                    "SELECT to_jsonb(t)::text FROM {}.{} t ORDER BY to_jsonb(t)::text"
                ).format(sql.Identifier(schema), sql.Identifier(table))
            ).fetchall()
            result[table] = hashlib.sha256(json.dumps(data).encode()).hexdigest()
        return result

    manager = Browser(base)
    manager.login("synthetic.manager.a", password)
    assert manager.request("/api/clients/")[0] == 200
    assert manager.request("/api/audit/")[0] == 200
    organizations = manager.request("/api/auth/access/")[1]["assignments"]
    org = next(
        g["organization_id"]
        for g in organizations
        if "users.manage" in g["permissions"]
    )
    if args.phase == "stage":
        with psycopg.connect(**connection_args(admin), autocommit=True) as conn:
            state["clients"] = hashes(conn, "clients_%", "public")
            state["integration"] = hashes(conn, "ingestion_%", "aiced_integration")
        state.update(
            username="synthetic.s5.local." + uuid.uuid4().hex[:10],
            password=secrets.token_urlsafe(32),
            organization_id=org,
        )
        created = manager.request(
            f"/api/organizations/{org}/users/",
            {"username": state["username"], "password": state["password"]},
        )
        assert created[0] == 201
        state["user_id"] = created[1]["user_id"]
        member = created[1]["id"]
        roles = manager.request(f"/api/organizations/{org}/roles/")[1]
        role = next(
            r
            for r in roles
            if "clients.view" in r["permissions"]
            and "users.manage" not in r["permissions"]
        )
        grant = manager.request(
            f"/api/organizations/{org}/role-assignments/",
            {"membership_id": member, "role_id": role["id"], "scope": "organization"},
        )
        assert grant[0] == 201
        b = Browser(base)
        b.login(state["username"], state["password"])
        assert b.request("/api/clients/")[0] == 200
        assert (
            manager.request(
                f"/api/organizations/{org}/role-assignments/{grant[1]['id']}/",
                data=b"",
                method="DELETE",
            )[0]
            == 204
        )
        assert b.request("/api/clients/")[0] == 403
        state["revoked_session"] = next(c.value for c in b.jar if c.name == "sessionid")
        assert b.request("/api/auth/logout/", {})[0] == 204
        state["iam_only_user"] = "synthetic.s5.iamonly.local." + uuid.uuid4().hex[:8]
        assert (
            manager.request(
                f"/api/organizations/{org}/users/",
                {"username": state["iam_only_user"], "password": state["password"]},
            )[0]
            == 201
        )
        b = Browser(base)
        b.login(state["iam_only_user"], state["password"])
        assert b.request("/api/session/")[0] == 200
        state["valid_session"] = next(c.value for c in b.jar if c.name == "sessionid")
    elif args.phase == "rollback":
        b = Browser(base)
        b.login(state["username"], state["password"])
        assert b.request("/api/clients/")[0] == 403
        b.login(state["iam_only_user"], state["password"])
        assert b.request("/api/session/")[0] == 200
        state["rollback_user"] = "synthetic.s5.rollback.local." + uuid.uuid4().hex[:8]
        assert (
            manager.request(
                f"/api/organizations/{org}/users/",
                {"username": state["rollback_user"], "password": state["password"]},
            )[0]
            == 201
        )
    else:
        b = Browser(base)
        b.login(state["rollback_user"], state["password"])
        assert b.request("/api/session/")[0] == 200
        b.login(state["username"], state["password"])
        assert b.request("/api/clients/")[0] == 403
        assert (
            Browser(base).request(
                "/api/session/",
                headers={"Cookie": "sessionid=" + state["valid_session"]},
            )[0]
            == 200
        )
        with psycopg.connect(**connection_args(admin), autocommit=True) as conn:
            assert state["clients"] == hashes(conn, "clients_%", "public")
            assert state["integration"] == hashes(
                conn, "ingestion_%", "aiced_integration"
            )
        for child, blocked in [
            (
                json.loads((directory / "iam-env.json").read_text()),
                [
                    "public.clients_party",
                    "public.identity_user",
                    "aiced_integration.ingestion_importbatch",
                ],
            ),
            (
                json.loads((directory / "backend-env.json").read_text()),
                [
                    "aiced_iam.identity_user",
                    "aiced_iam.django_session",
                    "public.identity_user",
                ],
            ),
        ]:
            with psycopg.connect(**connection_args(child), autocommit=True) as conn:
                for table in blocked:
                    for query in [
                        "SELECT * FROM " + table + " LIMIT 0",
                        "INSERT INTO " + table + " DEFAULT VALUES",
                    ]:
                        try:
                            conn.execute(query)
                        except psycopg.errors.InsufficientPrivilege:
                            pass
                        else:
                            raise AssertionError("Unexpected foreign data access")
    assert (
        Browser(base).request(
            "/api/session/", headers={"Cookie": "sessionid=" + state["revoked_session"]}
        )[0]
        == 403
    )
    it = Browser(base)
    it.login("synthetic.it.a", password)
    assert it.request("/api/clients/")[0] == 403
    op = Browser(base)
    op.login("synthetic.operator.a", password)
    assert op.request("/api/imports/context/")[0] == 200
    state[args.phase] = "passed"
    write(path, state)
    print(
        "S5 local "
        + args.phase
        + ": Gateway, IAM writes/revocation, audit, permissions and preserved data verified."
    )


if __name__ == "__main__":
    main()
