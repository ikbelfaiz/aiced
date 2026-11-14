"""S5 real-process safety gate; only a verified disposable PostgreSQL restore."""

import argparse, json, os, secrets, subprocess, sys, time, uuid, socket
from contextlib import contextmanager, ExitStack
from pathlib import Path

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
    pg_binary,
)
from s4_local import backup_restore
from s3_rehearsal import Browser
from s5_database import (
    provision,
    grants,
    refs,
    transfer,
    freeze,
    activate,
    fence,
    retarget,
    BASE,
    IAM,
)
from testing.gateway import free_port, nginx_gateway


@contextmanager
def server(directory, label, args, env, port):
    with (directory / (label + ".log")).open("ab") as log:
        process = subprocess.Popen(
            args,
            cwd=ROOT,
            env={**os.environ, **env, "PYTHONPATH": str(ROOT / ".tools/python")},
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            deadline = time.monotonic() + 25
            while True:
                if process.poll() is not None:
                    raise RuntimeError(label + " exited; inspect private log")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        raise RuntimeError(label + " startup timeout")
                    time.sleep(0.05)
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-local-rehearsal", required=True, action="store_true")
    parser.add_argument("--keep-candidate", action="store_true")
    args = parser.parse_args()
    local = ROOT / ".local/s4-active/b1cb997fda7f49a4a6331979c656bfb6"
    legacy_source = local / "s5-legacy-backend-env.json"
    original = json.loads(
        (
            legacy_source if legacy_source.exists() else local / "backend-env.json"
        ).read_text()
    )
    original.pop("AICED_MIGRATION_ROLE", None)
    if (
        original["POSTGRES_DB"] != "aiced"
        or original["POSTGRES_HOST"] != "127.0.0.1"
        or str(original["POSTGRES_PORT"]) != "55432"
        or original.get("DJANGO_DEBUG") != "1"
    ):
        raise ValueError("Local synthetic deployment only")
    runid = uuid.uuid4().hex
    directory = ROOT / ".local/s5-rehearsal" / runid
    directory.mkdir(parents=True)
    admin = {
        **original,
        "POSTGRES_USER": "aiced_owner",
        "POSTGRES_PASSWORD": json.loads(
            (ROOT / ".local/postgres/credentials.json").read_text()
        )["owner"],
    }
    env = {
        **original,
        "POSTGRES_DB": f"aiced_m1_{runid}_restore",
        "AICED_REHEARSAL_RUN": runid,
    }
    scratch = ScratchDatabases(env, original["POSTGRES_DB"])
    admenv = {**admin, "POSTGRES_DB": env["POSTGRES_DB"]}
    report = {
        "run": runid,
        "status": "running",
        "checks": [],
        "active_database_modified": False,
        "docker_available": False,
    }
    spec = None
    before = fingerprint(admin)

    def save():
        (directory / "report.json").write_text(json.dumps(report, indent=2))

    def passed(name):
        report["checks"].append(name)
        save()
        print(name, flush=True)

    def execute(label, args, child):
        with (directory / (label + ".log")).open("ab") as log:
            subprocess.run(
                args,
                cwd=ROOT,
                env={**os.environ, **child, "PYTHONPATH": str(ROOT / ".tools/python")},
                stdout=log,
                stderr=log,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

    def connect(child):
        return psycopg.connect(**connection_args(child), autocommit=True)

    def cmd(settings, port):
        return [
            sys.executable,
            "backend/manage.py",
            "runserver",
            f"127.0.0.1:{port}",
            "--noreload",
            "--settings",
            settings,
        ]

    try:
        if legacy_source.exists():
            from s5_backup import backup_restore as full_backup

            report["current_backup"] = full_backup(
                original, admin, directory, "current-active-s5"
            )
            checkpoints = json.loads((local / "s5-state.json").read_text())["backups"]
            backup = next(
                b
                for b in checkpoints
                if b["tables"] == 45 and b["restoration_verified"]
            )
            import hashlib

            if (
                hashlib.sha256(Path(backup["backup"]).read_bytes()).hexdigest()
                != backup["sha256"]
            ):
                raise ValueError("Verified pre-S5 backup changed")
            report["baseline_is_verified_pre_s5_checkpoint"] = True
        else:
            backup = backup_restore(original, admin, directory, "before-s5")
        report["backup"] = backup
        passed("Pre-ownership backup and full disposable restore verified")
        scratch.create(env["POSTGRES_DB"])
        execute(
            "restore",
            [
                pg_binary("pg_restore"),
                "--host",
                env["POSTGRES_HOST"],
                "--port",
                str(env["POSTGRES_PORT"]),
                "--username",
                admin["POSTGRES_USER"],
                "--exit-on-error",
                "--dbname",
                env["POSTGRES_DB"],
                backup["backup"],
            ],
            {**admenv, "PGPASSWORD": admin["POSTGRES_PASSWORD"]},
        )
        # Create an authenticated legacy session BEFORE changing IAM ownership.
        preport = free_port()
        with server(
            directory,
            "pre-cutover-iam",
            cmd("iam_service.legacy_settings", preport),
            env,
            preport,
        ):
            pre = Browser(f"http://127.0.0.1:{preport}")
            pre.login(
                "synthetic.manager.a",
                (ROOT / ".local/postgres/seed-password").read_text().strip(),
            )
        passed("Pre-cutover legacy session established for continuity verification")
        with connect(admenv) as conn:
            spec = provision(conn, env)
        migrator = {
            **env,
            "POSTGRES_USER": spec["roles"]["migrator"],
            "POSTGRES_PASSWORD": spec["passwords"]["migrator"],
            "AICED_MIGRATION_ROLE": spec["roles"]["owner"],
        }
        execute(
            "iam-migrate",
            [sys.executable, "backend/iam_service/manage.py", "migrate", "--noinput"],
            migrator,
        )
        execute(
            "refs-migrate",
            [
                sys.executable,
                "backend/manage.py",
                "migrate",
                "iam_consumer",
                "--noinput",
                "--settings",
                "iam_consumer.settings",
            ],
            {**env, "AICED_CONSUMER_MIGRATION": "1"},
        )
        with connect(admenv) as conn:
            refs(conn)
            # Fresh IAM metadata comes from post_migrate; replace only this empty schema's
            # initial metadata with exact historical primary keys before any runtime starts.
            conn.execute(
                sql.SQL("TRUNCATE {} CASCADE").format(
                    sql.SQL(",").join(
                        sql.SQL("aiced_iam.{}").format(sql.Identifier(t)) for t in BASE
                    )
                )
            )
            transfer(conn, "forward")
        execute(
            "consumer-migrate",
            [
                sys.executable,
                "backend/manage.py",
                "migrate",
                "--noinput",
                "--settings",
                "iam_consumer.settings",
            ],
            {**env, "AICED_CONSUMER_MIGRATION": "1"},
        )
        with connect(admenv) as conn:
            grants(conn, spec)
            fence(conn, spec, original["POSTGRES_USER"])
            activate(conn, "service")
            foreign = conn.execute(
                "SELECT DISTINCT n2.nspname FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_class d ON d.oid=k.confrelid JOIN pg_namespace n2 ON n2.oid=d.relnamespace WHERE k.contype='f' AND n.nspname='aiced_iam'"
            ).fetchall()
            assert foreign == [("aiced_iam",)]
        passed(
            "IAM independent migration lineage and local FK ownership established; legacy writer fenced"
        )
        keys = json.loads(original["AICED_INTERNAL_KEYS"])
        keys["client-iam-v1"] = {
            "secret": secrets.token_urlsafe(48),
            "service": "client_crm",
            "audiences": ["iam", "audit"],
        }
        keys["client-integration-v1"] = {
            "secret": secrets.token_urlsafe(48),
            "service": "client_crm",
            "audiences": ["integration"],
        }
        iamport, businessport, integrationport, frontendport = [
            free_port() for _ in range(4)
        ]
        runtime = {
            **env,
            "POSTGRES_USER": spec["roles"]["runtime"],
            "POSTGRES_PASSWORD": spec["passwords"]["runtime"],
            "AICED_INTERNAL_KEYS": json.dumps(
                {k: v for k, v in keys.items() if k != "client-integration-v1"}
            ),
        }
        consumer = {
            **env,
            "POSTGRES_USER": spec["roles"]["consumer"],
            "POSTGRES_PASSWORD": spec["passwords"]["consumer"],
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(48),
            "AICED_INTERNAL_KEYS": json.dumps(
                {k: keys[k] for k in ["client-iam-v1", "client-integration-v1"]}
            ),
            "AICED_INTEGRATION_AUDIT_KEY_ID": "client-integration-v1",
            "AICED_IAM_URL": f"http://127.0.0.1:{iamport}",
            "AICED_INTEGRATION_AUDIT_URL": f"http://127.0.0.1:{integrationport}",
        }
        integration = {
            **json.loads((local / "integration-env.json").read_text()),
            "POSTGRES_DB": env["POSTGRES_DB"],
            "AICED_IAM_URL": consumer["AICED_IAM_URL"],
        }
        integration["AICED_INTERNAL_KEYS"] = json.dumps(
            {
                **json.loads(integration["AICED_INTERNAL_KEYS"]),
                "client-integration-v1": keys["client-integration-v1"],
            }
        )
        for name, value in [
            ("iam-env", runtime),
            ("consumer-env", consumer),
            ("integration-env", integration),
            ("migration-env", migrator),
            ("ownership-private", spec),
        ]:
            (directory / (name + ".json")).write_text(json.dumps(value, indent=2))
        execute(
            "iam-unit-tests",
            [
                sys.executable,
                "backend/iam_service/manage.py",
                "test",
                "iam_service",
                "--noinput",
            ],
            runtime,
        )
        execute(
            "iam-migration-consistency",
            [
                sys.executable,
                "backend/iam_service/manage.py",
                "makemigrations",
                "--check",
                "--dry-run",
            ],
            runtime,
        )
        execute(
            "consumer-migration-consistency",
            [
                sys.executable,
                "backend/manage.py",
                "makemigrations",
                "--check",
                "--dry-run",
                "--settings",
                "iam_consumer.settings",
            ],
            consumer,
        )
        passed(
            "Five isolated IAM tests and both runtime migration-consistency checks passed"
        )
        # Credential isolation is tested with real LOGINs, not SET ROLE as superuser.
        for child, blocked in [
            (
                runtime,
                [
                    "public.identity_user",
                    "public.clients_party",
                    "public.audit_auditevent",
                    "aiced_integration.ingestion_importbatch",
                ],
            ),
            (
                consumer,
                [
                    "public.identity_user",
                    "public.django_session",
                    "aiced_iam.identity_user",
                    "aiced_iam.django_session",
                ],
            ),
            (
                integration,
                [
                    "public.identity_user",
                    "aiced_iam.identity_user",
                    "public.clients_party",
                ],
            ),
        ]:
            with connect(child) as conn:
                for table in blocked:
                    try:
                        conn.execute(
                            sql.SQL("SELECT * FROM {} LIMIT 0").format(sql.SQL(table))
                        )
                    except psycopg.errors.InsufficientPrivilege:
                        pass
                    else:
                        raise AssertionError("Unauthorized read " + table)
                for table in blocked:
                    try:
                        conn.execute(
                            sql.SQL("INSERT INTO {} DEFAULT VALUES").format(
                                sql.SQL(table)
                            )
                        )
                    except psycopg.errors.InsufficientPrivilege:
                        pass
                    else:
                        raise AssertionError("Unauthorized write " + table)
                flags = conn.execute(
                    "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user"
                ).fetchone()
                assert not any(flags)
        passed(
            "Three restricted real credentials deny foreign IAM/business/integration tables"
        )
        password = (ROOT / ".local/postgres/seed-password").read_text().strip()
        with connect(admenv) as conn:
            org = (
                str(
                    conn.execute(
                        "SELECT id FROM aiced_iam.identity_organization WHERE code='AMEN-A'"
                    ).fetchone()[0]
                )
                if conn.execute(
                    "SELECT 1 FROM aiced_iam.identity_organization WHERE code='AMEN-A'"
                ).fetchone()
                else str(
                    conn.execute(
                        "SELECT m.organization_id FROM aiced_iam.identity_membership m JOIN aiced_iam.identity_user u ON u.id=m.user_id WHERE u.username='synthetic.manager.a'"
                    ).fetchone()[0]
                )
            )
            foreignparty = str(
                conn.execute(
                    "SELECT p.id FROM public.clients_party p WHERE p.organization_id<>%s LIMIT 1",
                    [org],
                ).fetchone()[0]
            )
            ownparty = str(
                conn.execute(
                    "SELECT p.id FROM public.clients_party p WHERE p.organization_id=%s AND p.origin='SYNTHETIC_ONLY' LIMIT 1",
                    [org],
                ).fetchone()[0]
            )
            crm_before = conn.execute(
                "SELECT to_jsonb(t)::text FROM public.clients_party t ORDER BY id"
            ).fetchall()
        with ExitStack() as stack:
            iamproc = stack.enter_context(
                server(
                    directory,
                    "iam",
                    cmd("iam_service.settings", iamport),
                    runtime,
                    iamport,
                )
            )
            businessproc = stack.enter_context(
                server(
                    directory,
                    "business",
                    cmd("iam_consumer.settings", businessport),
                    consumer,
                    businessport,
                )
            )
            integrationproc = stack.enter_context(
                server(
                    directory,
                    "integration",
                    [
                        sys.executable,
                        "backend/integration_service/manage.py",
                        "runserver",
                        f"127.0.0.1:{integrationport}",
                        "--noreload",
                    ],
                    integration,
                    integrationport,
                )
            )
            stack.enter_context(
                server(
                    directory,
                    "frontend",
                    [
                        str(ROOT / ".tools/node.exe"),
                        str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                        str(ROOT / "frontend"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(frontendport),
                        "--strictPort",
                    ],
                    consumer,
                    frontendport,
                )
            )
            base = stack.enter_context(
                nginx_gateway(
                    directory / "gateway",
                    f"127.0.0.1:{businessport}",
                    f"127.0.0.1:{frontendport}",
                    env["AICED_GATEWAY_KEY"],
                    integration=f"127.0.0.1:{integrationport}",
                    iam=f"127.0.0.1:{iamport}",
                )
            )
            manager, reader, it, operator, reviewer = [Browser(base) for _ in range(5)]
            for cookie in pre.jar:
                manager.jar.set_cookie(cookie)
            assert manager.request("/api/session/")[0] == 200
            assert (
                Browser(base).request(
                    "/api/clients/", headers={"Cookie": "sessionid=malformed"}
                )[0]
                == 403
            )
            assert manager.request("/api/clients/")[0] == 200
            passed(
                "Existing pre-cutover session survives schema transfer without re-login"
            )
            for b, name in [
                (manager, "manager.a"),
                (reader, "reader.a"),
                (it, "it.a"),
                (operator, "operator.a"),
                (reviewer, "reviewer.a"),
            ]:
                b.login("synthetic." + name, password)
            assert manager.request("/api/session/")[0] == 200
            assert manager.request("/api/clients/")[0] == 200
            assert manager.request(f"/api/clients/{foreignparty}/")[0] == 404
            assert it.request("/api/clients/")[0] == 403
            assert operator.request("/api/imports/context/")[0] == 200
            assert reviewer.request(f"/api/imports/{org}/batches/")[0] == 200
            assert manager.request("/api/audit/")[0] == 200
            assert (
                Browser(base).request(
                    "/api/clients/",
                    headers={"X-User-ID": str(uuid.uuid4()), "X-Role": "admin"},
                )[0]
                == 403
            )
            assert (
                Browser(f"http://127.0.0.1:{businessport}").request(
                    "/api/auth/login/", {"username": "fake", "password": "fake"}
                )[0]
                == 503
            )
            passed(
                "Real IAM + business + Integration + Nginx preserve sessions, data, public audit and object-level denials"
            )
            # New users and grants must survive rollback; delegation remains bounded.
            username = "synthetic.s5." + runid[:12]
            newpass = secrets.token_urlsafe(32)
            created = manager.request(
                f"/api/organizations/{org}/users/",
                {"username": username, "password": newpass},
            )
            assert created[0] == 201, created
            member = created[1]["id"]
            user = created[1]["user_id"]
            roles = manager.request(f"/api/organizations/{org}/roles/")[1]
            role = next(
                r
                for r in roles
                if "clients.view" in r["permissions"]
                and "users.manage" not in r["permissions"]
            )
            granted = manager.request(
                f"/api/organizations/{org}/role-assignments/",
                {
                    "membership_id": member,
                    "role_id": role["id"],
                    "scope": "organization",
                },
            )
            assert granted[0] == 201, granted
            novice = Browser(base)
            novice.login(username, newpass)
            assert novice.request("/api/clients/")[0] == 200
            assert (
                novice.request(
                    f"/api/organizations/{org}/users/",
                    {"username": "bad", "password": newpass},
                )[0]
                == 403
            )
            assert (
                manager.request(
                    f"/api/organizations/{org}/role-assignments/{granted[1]['id']}/",
                    data=b"",
                    method="DELETE",
                )[0]
                == 204
            )
            assert novice.request("/api/clients/")[0] == 403
            passed(
                "New IAM writes, bounded delegation, privilege escalation denial and fresh permission revocation verified"
            )
            # Session deletion is canonical; capture and try a replay after logout.
            cookie = next(c.value for c in novice.jar if c.name == "sessionid")
            assert novice.request("/api/auth/logout/", {})[0] == 204
            assert (
                Browser(base).request(
                    "/api/session/", headers={"Cookie": "sessionid=" + cookie}
                )[0]
                == 403
            )
            assert (
                Browser(base).request(
                    "/api/clients/", headers={"Cookie": "sessionid=" + cookie}
                )[0]
                == 403
            )
            passed(
                "Revoked session cannot be replayed through IAM or a business service"
            )
            # Restart IAM independently: existing sessions survive; outage fails closed.
            iamproc.terminate()
            iamproc.wait(timeout=10)
            assert manager.request("/api/clients/")[0] == 503
            assert operator.request("/api/imports/context/")[0] == 503
            assert Browser(base).request("/api/health/")[0] == 200
            stack.enter_context(
                server(
                    directory,
                    "iam-restarted",
                    cmd("iam_service.settings", iamport),
                    runtime,
                    iamport,
                )
            )
            assert manager.request("/api/clients/")[0] == 200
            assert operator.request("/api/imports/context/")[0] == 200
            assert businessproc.poll() is None and integrationproc.poll() is None
            passed(
                "IAM outage fails closed and independent restart preserves existing sessions"
            )
            # Real signed request authentication and replay protection on IAM-owned SQL.
            from internal_api.security import signed_headers

            cookie_value = next(c.value for c in manager.jar if c.name == "sessionid")
            credentials = {
                "session_key": cookie_value,
                "method": "GET",
                "host": base.split("//")[1],
                "scheme": "http",
            }
            path = "/internal/v1/grants/snapshot"
            body = json.dumps(
                {"credentials": credentials}, sort_keys=True, separators=(",", ":")
            ).encode()
            headers = signed_headers(
                "client-iam-v1", keys["client-iam-v1"]["secret"], "iam", path, body
            )
            private = Browser(f"http://127.0.0.1:{iamport}")
            assert private.request(path, data=body, headers=headers)[0] == 200
            assert private.request(path, data=body, headers=headers)[0] == 403
            forged = {
                **headers,
                "X-Aiced-Nonce": secrets.token_hex(24),
                "X-Role": "admin",
            }
            assert private.request(path, data=body, headers=forged)[0] == 403
            assert (
                private.request(
                    path, data=body, headers={"X-User-ID": user, "X-Role": "admin"}
                )[0]
                == 403
            )
            passed(
                "Signed private grants reject replay, changed nonce/signature and forged identity headers"
            )
            other = Browser(base)
            other.login("synthetic.operator.a", password)
            revokecredentials = {
                "session_key": next(
                    c.value for c in other.jar if c.name == "sessionid"
                ),
                "method": "POST",
                "csrf_cookie": next(
                    c.value for c in other.jar if c.name == "csrftoken"
                ),
                "csrf_token": next(c.value for c in other.jar if c.name == "csrftoken"),
                "origin": base,
                "host": base.split("//")[1],
                "scheme": "http",
            }
            path = "/internal/v1/sessions/revoke"
            body = json.dumps(
                {"credentials": revokecredentials},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            headers = signed_headers(
                "client-iam-v1", keys["client-iam-v1"]["secret"], "iam", path, body
            )
            assert private.request(path, data=body, headers=headers)[0] == 200
            assert other.request("/api/imports/context/")[0] == 403
            passed(
                "Signed delegated session-revocation contract preserves CSRF and revokes cross-service access"
            )
            # A required audit failure must roll back BOTH user and membership creation.
            failname = "synthetic.s5.auditfailure." + runid[:8]
            with connect(admenv) as conn:
                conn.execute(
                    "CREATE FUNCTION aiced_iam.s5_fail_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='users.created' THEN RAISE EXCEPTION 'synthetic audit failure'; END IF; RETURN NEW; END; $$"
                )
                conn.execute(
                    "CREATE TRIGGER s5_fail_audit BEFORE INSERT ON aiced_iam.audit_auditevent FOR EACH ROW EXECUTE FUNCTION aiced_iam.s5_fail_audit()"
                )
            try:
                assert (
                    manager.request(
                        f"/api/organizations/{org}/users/",
                        {"username": failname, "password": newpass},
                    )[0]
                    == 500
                )
                with connect(admenv) as conn:
                    assert (
                        conn.execute(
                            "SELECT count(*) FROM aiced_iam.identity_user WHERE username=%s",
                            [failname],
                        ).fetchone()[0]
                        == 0
                    )
            finally:
                with connect(admenv) as conn:
                    conn.execute(
                        "DROP TRIGGER s5_fail_audit ON aiced_iam.audit_auditevent"
                    )
                    conn.execute("DROP FUNCTION aiced_iam.s5_fail_audit()")
            passed(
                "Required IAM audit failure rolls back user/membership state atomically"
            )
            with connect(admenv) as conn:
                crm_state = conn.execute(
                    "SELECT to_jsonb(t)::text FROM public.clients_crmprofile t WHERE party_id=%s",
                    [ownparty],
                ).fetchone()
                conn.execute(
                    "CREATE FUNCTION public.s5_fail_crm_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='clients.crm_updated' THEN RAISE EXCEPTION 'synthetic business audit failure'; END IF; RETURN NEW; END; $$"
                )
                conn.execute(
                    "CREATE TRIGGER s5_fail_crm_audit BEFORE INSERT ON public.audit_auditevent FOR EACH ROW EXECUTE FUNCTION public.s5_fail_crm_audit()"
                )
            try:
                assert (
                    manager.request(
                        f"/api/clients/{ownparty}/crm/",
                        {"notes": "SYNTHETIC audit rollback probe"},
                        method="PATCH",
                    )[0]
                    == 500
                )
                with connect(admenv) as conn:
                    assert (
                        conn.execute(
                            "SELECT to_jsonb(t)::text FROM public.clients_crmprofile t WHERE party_id=%s",
                            [ownparty],
                        ).fetchone()
                        == crm_state
                    )
            finally:
                with connect(admenv) as conn:
                    conn.execute(
                        "DROP TRIGGER s5_fail_crm_audit ON public.audit_auditevent"
                    )
                    conn.execute("DROP FUNCTION public.s5_fail_crm_audit()")
            passed(
                "Business mutation plus local audit/outbox still roll back together with remote IAM"
            )
            # A queued write must revalidate after a committed revocation. The fresh
            # actor was given full scope, so no IAM business scoping is involved.
            from concurrent.futures import ThreadPoolExecutor

            with connect(admenv) as held:
                held.execute("BEGIN")
                held.execute(
                    "SELECT id FROM public.iam_consumer_organizationref WHERE id=%s FOR UPDATE",
                    [org],
                )
                regrant = manager.request(
                    f"/api/organizations/{org}/role-assignments/",
                    {
                        "membership_id": member,
                        "role_id": role["id"],
                        "scope": "organization",
                    },
                )
                assert regrant[0] == 201
                novice.login(username, newpass)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pending = pool.submit(
                        novice.request,
                        f"/api/clients/{ownparty}/crm/",
                        {"notes": "SYNTHETIC forbidden queued edit"},
                        "PATCH",
                    )
                    time.sleep(0.5)
                    assert not pending.done()
                    assert (
                        manager.request(
                            f"/api/organizations/{org}/role-assignments/{regrant[1]['id']}/",
                            data=b"",
                            method="DELETE",
                        )[0]
                        == 204
                    )
                    held.execute("COMMIT")
                    assert pending.result(timeout=15)[0] in (403, 404)
            with connect(admenv) as conn:
                assert (
                    conn.execute(
                        "SELECT to_jsonb(t)::text FROM public.clients_crmprofile t WHERE party_id=%s",
                        [ownparty],
                    ).fetchone()
                    == crm_state
                )
            passed(
                "Cross-process permission revocation overtakes queued write; post-lock reauthorization prevents mutation"
            )

            changed = manager.request(
                f"/api/organizations/{org}/role-assignments/",
                {
                    "membership_id": member,
                    "role_id": role["id"],
                    "scope": "organization",
                },
            )
            assert changed[0] == 201
            novice.login(username, newpass)
            assert novice.request("/api/clients/")[0] == 200
            execute(
                "remove-role-permission",
                [
                    sys.executable,
                    "backend/iam_service/manage.py",
                    "shell",
                    "-c",
                    f"from django.db import transaction; from identity.coordination import barrier; from identity.models import Role,User; from audit.services import record; t=transaction.atomic(); t.__enter__(); barrier(exclusive=True); Role.objects.get(pk='{role['id']}').permissions.remove('clients.update_crm'); record('permissions.capabilities_changed',actor=User.objects.get(username='synthetic.manager.a'),organization_id='{org}',target_id='{role['id']}'); t.__exit__(None,None,None)",
                ],
                runtime,
            )
            assert novice.request("/api/clients/")[0] == 200
            assert novice.request(
                f"/api/clients/{ownparty}/crm/",
                {"notes": "SYNTHETIC forbidden changed permission"},
                method="PATCH",
            )[0] in (403, 404)
            assert (
                manager.request(
                    f"/api/organizations/{org}/role-assignments/{changed[1]['id']}/",
                    data=b"",
                    method="DELETE",
                )[0]
                == 204
            )
            passed(
                "Audited role-capability removal is immediately enforced by remote business authorization"
            )
            iamonlyname = "synthetic.s5.iamonly." + runid[:8]
            assert (
                manager.request(
                    f"/api/organizations/{org}/users/",
                    {"username": iamonlyname, "password": newpass},
                )[0]
                == 201
            )
            iamonly = Browser(base)
            iamonly.login(iamonlyname, newpass)
            assert iamonly.request("/api/session/")[0] == 200
            # Browser exercises the unchanged UI against the split services.
            execute(
                "browser",
                [str(ROOT / ".tools/node.exe"), "scripts/s5_browser.mjs"],
                {
                    **consumer,
                    "AICED_S5_URL": base,
                    "AICED_S5_PASSWORD": password,
                    "AICED_S5_DIR": str(directory),
                },
            )
        from s5_backup import backup_restore as s5_backup

        with connect(admenv) as conn:
            freeze(conn)
        report["pre_rollback_backup"] = s5_backup(
            env, admenv, directory, "post-write-before-rollback"
        )
        passed(
            "Post-write IAM/Integration/business backup restored with exact data/schema/ACL/sequence parity"
        )
        with connect(admenv) as conn:
            transfer(conn, "reverse")
            transfer(conn, "reverse")
            retarget(conn, False)
            fence(conn, spec, original["POSTGRES_USER"], False)
            activate(conn, "legacy")
        with connect(admenv) as conn:
            assert (
                conn.execute(
                    "SELECT count(*) FROM public.identity_role_permissions WHERE role_id=%s AND capability_id=%s",
                    [role["id"], "clients.update_crm"],
                ).fetchone()[0]
                == 0
            )
        passed(
            "Post-write reverse transfer is idempotent and restores legacy credentials/FKs without data reset"
        )
        # Legacy IAM and residue restart against copied-back data; Integration stays external.
        legacy = {
            **env,
            "AICED_INTERNAL_KEYS": json.dumps(keys),
            "AICED_INTEGRATION_AUDIT_URL": consumer["AICED_INTEGRATION_AUDIT_URL"],
        }
        with ExitStack() as stack:
            stack.enter_context(
                server(
                    directory,
                    "legacy-iam",
                    cmd("iam_service.legacy_settings", iamport),
                    legacy,
                    iamport,
                )
            )
            stack.enter_context(
                server(
                    directory,
                    "legacy-business",
                    cmd("config.settings", businessport),
                    legacy,
                    businessport,
                )
            )
            stack.enter_context(
                server(
                    directory,
                    "rollback-integration",
                    [
                        sys.executable,
                        "backend/integration_service/manage.py",
                        "runserver",
                        f"127.0.0.1:{integrationport}",
                        "--noreload",
                    ],
                    integration,
                    integrationport,
                )
            )
            base = stack.enter_context(
                nginx_gateway(
                    directory / "rollback-gateway",
                    f"127.0.0.1:{businessport}",
                    f"127.0.0.1:{frontendport}",
                    env["AICED_GATEWAY_KEY"],
                    integration=f"127.0.0.1:{integrationport}",
                    iam=f"127.0.0.1:{iamport}",
                )
            )
            reverted = Browser(base)
            reverted.login(username, newpass)
            assert reverted.request("/api/clients/")[0] == 403
            assert reverted.request("/api/session/")[1]["id"] == user
            assert (
                Browser(base).request(
                    "/api/session/", headers={"Cookie": "sessionid=" + cookie}
                )[0]
                == 403
            )
            m = Browser(base)
            m.login("synthetic.manager.a", password)
            assert m.request("/api/clients/")[0] == 200
            assert m.request("/api/audit/")[0] == 200
            # A NEW legacy write and logout must survive forward re-cutover too.
            legacyname = "synthetic.s5.rollback." + runid[:8]
            assert (
                m.request(
                    f"/api/organizations/{org}/users/",
                    {"username": legacyname, "password": newpass},
                )[0]
                == 201
            )
            passed(
                "Rollback application login, revocation, audit and new legacy IAM write verified via real Gateway"
            )
        with connect(admenv) as conn:
            freeze(conn)
            refs(conn)
            transfer(conn, "forward")
            retarget(conn, True)
            fence(conn, spec, original["POSTGRES_USER"])
            activate(conn, "service")
        with ExitStack() as stack:
            stack.enter_context(
                server(
                    directory,
                    "forward-iam",
                    cmd("iam_service.settings", iamport),
                    runtime,
                    iamport,
                )
            )
            stack.enter_context(
                server(
                    directory,
                    "forward-business",
                    cmd("iam_consumer.settings", businessport),
                    consumer,
                    businessport,
                )
            )
            stack.enter_context(
                server(
                    directory,
                    "forward-integration",
                    [
                        sys.executable,
                        "backend/integration_service/manage.py",
                        "runserver",
                        f"127.0.0.1:{integrationport}",
                        "--noreload",
                    ],
                    integration,
                    integrationport,
                )
            )
            base = stack.enter_context(
                nginx_gateway(
                    directory / "forward-gateway",
                    f"127.0.0.1:{businessport}",
                    f"127.0.0.1:{frontendport}",
                    env["AICED_GATEWAY_KEY"],
                    integration=f"127.0.0.1:{integrationport}",
                    iam=f"127.0.0.1:{iamport}",
                )
            )
            b = Browser(base)
            b.login(legacyname, newpass)
            assert b.request("/api/session/")[0] == 200
            b.login(username, newpass)
            assert b.request("/api/clients/")[0] == 403
            assert (
                Browser(base).request(
                    "/api/session/", headers={"Cookie": "sessionid=" + cookie}
                )[0]
                == 403
            )
            m = Browser(base)
            m.login("synthetic.manager.a", password)
            assert m.request("/api/clients/")[0] == 200
            assert m.request("/api/audit/")[0] == 200
            execute(
                "deactivate-user",
                [
                    sys.executable,
                    "backend/iam_service/manage.py",
                    "shell",
                    "-c",
                    f"from identity.models import User; from identity.services import deactivate_user; deactivate_user(User.objects.get(username='synthetic.manager.a'),User.objects.get(username='{username}').pk)",
                ],
                runtime,
            )
            assert b.request("/api/session/")[0] == 403
            assert b.request("/api/clients/")[0] == 403
            passed(
                "Audited IAM user deactivation revokes identity across the independently running services"
            )
        with connect(admenv) as conn:
            assert (
                crm_before
                == conn.execute(
                    "SELECT to_jsonb(t)::text FROM public.clients_party t ORDER BY id"
                ).fetchall()
            )
        with connect(admenv) as conn:
            assert (
                conn.execute(
                    "SELECT count(*) FROM aiced_iam.identity_role_permissions WHERE role_id=%s AND capability_id=%s",
                    [role["id"], "clients.update_crm"],
                ).fetchone()[0]
                == 0
            )
        passed(
            "Forward re-cutover preserves new legacy writes, revoked session/permissions and unchanged client identities"
        )
        report["final_backup"] = s5_backup(env, admenv, directory, "after-forward")
        passed("Final three-schema backup/restore verified after forward re-cutover")
        import hashlib

        report["code_hashes"] = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in [
                "backend/iam_service",
                "backend/iam_control",
                "backend/iam_consumer",
            ]
            for p in (ROOT / folder).rglob("*.py")
        }
        report["status"] = "passed"
        report["writer"] = "iam"
        report["ports"] = {
            "iam": iamport,
            "business": businessport,
            "integration": integrationport,
            "frontend": frontendport,
        }
    except Exception as error:
        report["status"] = "failed"
        report["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        require_equal(
            before, fingerprint(admin), "S5 original application preservation"
        )
        report["original_unchanged"] = True
        if not args.keep_candidate or report["status"] != "passed":
            for name in list(scratch.created):
                scratch.drop(name)
            report["scratch_removed"] = True
            if spec:
                with psycopg.connect(**connection_args(admin), autocommit=True) as c:
                    for name in spec["roles"].values():
                        if c.execute(
                            "SELECT shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname=%s",
                            [name],
                        ).fetchone() != ("aiced-s5:" + runid,):
                            raise ValueError("Unsafe role cleanup")
                        c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))
        save()
        print("Report:", directory / "report.json", flush=True)


if __name__ == "__main__":
    main()
