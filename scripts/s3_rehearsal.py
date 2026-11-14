"""S3 safety gate: backup/restore first, isolated schema, real IAM/service/Gateway.

Only local DEBUG PostgreSQL and marked disposable restored databases. Existing
application data is read-only throughout. No active-domain cutover is performed.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from datetime import date
import hashlib
from http.cookiejar import CookieJar
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / ".tools/python"),
    str(ROOT / "backend"),
    str(ROOT / "scripts"),
]
import openpyxl
import psycopg
from psycopg import sql
from migration_baseline import (
    ScratchDatabases,
    connection_args,
    fingerprint,
    require_equal,
    pg_binary,
    canonical_constraint,
)
from testing.gateway import free_port, nginx_gateway
from ingestion.templates import TEMPLATES
from s3_database import (
    provision,
    grant_runtime,
    copy_restored,
    cleanup_roles,
    TABLES,
    SCHEMA,
)


class Browser:
    def __init__(self, base):
        self.base = base
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )

    def request(self, path, data=None, method=None, headers=None):
        headers = dict(headers or {})
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            headers.setdefault("Content-Type", "application/json")
        if data is not None:
            headers.setdefault(
                "X-CSRFToken",
                next((c.value for c in self.jar if c.name == "csrftoken"), ""),
            )
            headers.setdefault("Origin", self.base)
        request = urllib.request.Request(
            self.base + path, data=data, method=method, headers=headers
        )
        try:
            response = self.opener.open(request, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        raw = response.read()
        try:
            body = json.loads(raw)
        except ValueError:
            body = raw
        return response.status, body, response.headers

    def login(self, username, password):
        assert self.request("/api/auth/csrf/")[0] == 200
        assert (
            self.request(
                "/api/auth/login/", {"username": username, "password": password}
            )[0]
            == 200
        )
        assert self.request("/api/auth/csrf/")[0] == 200


def workbook(key):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = TEMPLATES["legal"]["sheet"]
    sheet.append(TEMPLATES["legal"]["headers"])
    for value in (key, "S3-DUP", "S3-DUP"):
        row = [None] * 25
        row[1], row[3] = value, "SOCIETE SYNTHETIQUE S3"
        sheet.append(row)
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-local-rehearsal", required=True, action="store_true")
    parser.add_argument(
        "--keep-candidate",
        action="store_true",
        help="Keep this marked restored candidate and private credentials after a successful rehearsal",
    )
    options = parser.parse_args()
    original = json.loads((ROOT / ".local/postgres/env.json").read_text())
    if (
        original.get("DJANGO_DEBUG") != "1"
        or original.get("POSTGRES_HOST") != "127.0.0.1"
        or str(original.get("POSTGRES_PORT")) != "55432"
    ):
        raise ValueError("Only the portable local development cluster is supported")
    run = uuid.uuid4().hex
    directory = ROOT / ".local/s3-rehearsal" / run
    directory.mkdir(parents=True, mode=0o700)
    env = {
        **original,
        "POSTGRES_DB": f"aiced_m1_{run}_restore",
        "AICED_REHEARSAL_RUN": run,
    }
    scratch = ScratchDatabases(env, original["POSTGRES_DB"])
    admin = {
        **env,
        "POSTGRES_USER": "aiced_owner",
        "POSTGRES_PASSWORD": json.loads(
            (ROOT / ".local/postgres/credentials.json").read_text()
        )["owner"],
    }
    child = {
        **os.environ,
        **env,
        "PYTHONPATH": str(ROOT / ".tools/python") + os.pathsep + str(ROOT / "backend"),
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "AICED_S3_PASSWORD": secrets.token_urlsafe(40),
        "AICED_S3_STATE": str(directory / "fixture.json"),
        "AICED_GATEWAY_KEY": secrets.token_urlsafe(48),
    }
    keys = {
        "integration-v1": {
            "secret": secrets.token_urlsafe(48),
            "service": "integration",
            "audiences": ["iam", "audit"],
        }
    }
    child["AICED_INTERNAL_KEYS"] = json.dumps(keys)
    report = {
        "run": run,
        "status": "running",
        "docker_available": bool(shutil.which("docker")),
        "application_cutover": False,
        "checks": [],
        "scratch_removed": False,
    }
    spec = None
    before = fingerprint(original)

    def save():
        (directory / "report.json").write_text(json.dumps(report, indent=2))

    def passed(name):
        report["checks"].append(name)
        print(name, flush=True)
        save()

    def execute(label, args, settings_env=None):
        with (directory / (label + ".log")).open("wb") as log:
            result = subprocess.run(
                args,
                cwd=ROOT,
                env=settings_env or child,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        if result.returncode:
            raise RuntimeError(label + " failed; inspect private log")

    @contextmanager
    def server(label, args, process_env, port, cwd=ROOT):
        with (directory / (label + ".log")).open("wb") as log:
            process = subprocess.Popen(
                args,
                cwd=cwd,
                env=process_env,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                deadline = time.monotonic() + 20
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(label + " exited; inspect private log")
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                            break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise RuntimeError(label + " failed to start")
                        time.sleep(0.05)
                yield process
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

    def runtime_connect():
        return psycopg.connect(
            **{
                **connection_args(env),
                "user": spec["roles"]["runtime"],
                "password": spec["passwords"]["runtime"],
            },
            autocommit=True,
        )

    def count(conn, table):
        return conn.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(SCHEMA), sql.Identifier(table)
            )
        ).fetchone()[0]

    try:
        # No schema/role/ownership writes before the full backup is restored and compared.
        pg = [
            "--host",
            original["POSTGRES_HOST"],
            "--port",
            str(original["POSTGRES_PORT"]),
            "--username",
            original["POSTGRES_USER"],
        ]
        pg_env = {**child, "PGPASSWORD": original["POSTGRES_PASSWORD"]}
        backup = directory / "before-s3.dump"
        execute(
            "backup",
            [
                pg_binary("pg_dump"),
                *pg,
                "--format=custom",
                "--file",
                str(backup),
                "--dbname",
                original["POSTGRES_DB"],
            ],
            pg_env,
        )
        scratch.create(env["POSTGRES_DB"])
        execute(
            "restore",
            [
                pg_binary("pg_restore"),
                *pg,
                "--exit-on-error",
                "--dbname",
                env["POSTGRES_DB"],
                str(backup),
            ],
            pg_env,
        )
        require_equal(before, fingerprint(env), "Exact backup restoration")
        report["backup_sha256"] = hashlib.sha256(backup.read_bytes()).hexdigest()
        passed(
            "existing backup restored with exact record/schema parity before provisioning"
        )
        execute(
            "synthetic-fixture",
            [sys.executable, "backend/testing/integration_fixture.py"],
        )
        state = json.loads((directory / "fixture.json").read_text())
        public_before_copy = fingerprint(env)
        with psycopg.connect(**connection_args(admin), autocommit=True) as conn:
            spec = provision(conn, env)
        integration_env = {
            **child,
            "DJANGO_SETTINGS_MODULE": "integration_service.settings",
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
            "POSTGRES_USER": spec["roles"]["runtime"],
            "POSTGRES_PASSWORD": spec["passwords"]["runtime"],
            "AICED_INTERNAL_KEYS": json.dumps(keys),
        }
        migrator = {
            **integration_env,
            "POSTGRES_USER": spec["roles"]["migrator"],
            "POSTGRES_PASSWORD": spec["passwords"]["migrator"],
            "AICED_MIGRATION_ROLE": spec["roles"]["owner"],
        }
        command = [sys.executable, "backend/integration_service/manage.py"]
        execute("integration-migrate", [*command, "migrate", "--noinput"], migrator)
        execute("integration-check", [*command, "check"], integration_env)
        execute(
            "integration-migration-consistency",
            [*command, "makemigrations", "--check", "--dry-run"],
            migrator,
        )
        execute(
            "integration-unit",
            [*command, "test", "integration_store", "--noinput"],
            integration_env,
        )
        with psycopg.connect(**connection_args(admin), autocommit=True) as conn:
            copy_restored(conn, env)
            grant_runtime(conn, spec)
            report["copied_counts"] = {table: count(conn, table) for table in TABLES}
            # Schema owns every persistent relation, including its migration recorder.
            owners = conn.execute(
                "SELECT DISTINCT pg_get_userbyid(c.relowner) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relkind IN ('r','S')",
                (SCHEMA,),
            ).fetchall()
            assert owners == [(spec["roles"]["owner"],)]
            foreign_keys = conn.execute(
                "SELECT n2.nspname FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_class c2 ON c2.oid=k.confrelid JOIN pg_namespace n2 ON n2.oid=c2.relnamespace WHERE n.nspname=%s AND k.contype='f'",
                (SCHEMA,),
            ).fetchall()
            assert foreign_keys and all(row[0] == SCHEMA for row in foreign_keys)
        # Only public schema ACL changed intentionally in this restored rehearsal.
        require_equal(
            public_before_copy,
            fingerprint(env),
            "Historical records and public migrations unchanged",
        )
        passed(
            "owned migrations, four exact table copies, local references and local-only foreign keys"
        )
        with runtime_connect() as conn:
            assert conn.execute("SELECT current_schema()").fetchone()[0] == SCHEMA
            assert (
                conn.execute(
                    "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user"
                ).fetchone()
                == (False,) * 5
            )
            forbidden = [
                "SELECT * FROM public.identity_user",
                "UPDATE public.identity_user SET is_active=false",
                "SELECT * FROM public.clients_party",
                "UPDATE public.clients_party SET version=version",
                "SELECT * FROM public.clients_opportunity",
                "UPDATE public.clients_opportunity SET amount=amount",
                "CREATE TABLE public.s3_forbidden(id int)",
                "CREATE TABLE aiced_integration.s3_forbidden(id int)",
                "CREATE TEMP TABLE s3_forbidden(id int)",
                "SET ROLE " + spec["roles"]["owner"],
                "DELETE FROM aiced_integration.integration_store_journal",
                "UPDATE aiced_integration.ingestion_stagingrow SET cells=cells",
            ]
            for statement in forbidden:
                try:
                    with conn.transaction():
                        conn.execute(statement)
                        raise AssertionError("Unauthorized SQL permitted")
                except psycopg.Error as error:
                    assert error.sqlstate == "42501", error.sqlstate
        passed(
            "real runtime LOGIN: IAM/Client/Commercial reads and writes, DDL, TEMP, SET ROLE, immutable updates denied"
        )
        iam_port, integration_port, backend_port, frontend_port = (
            free_port(),
            free_port(),
            free_port(),
            free_port(),
        )
        report["ports"] = {
            "iam": iam_port,
            "integration": integration_port,
            "backend": backend_port,
        }
        integration_env["AICED_IAM_URL"] = f"http://127.0.0.1:{iam_port}"
        # Persist only this service's credentials/config; never the IAM database password.
        private_env = {
            key: value
            for key, value in integration_env.items()
            if key.startswith(("POSTGRES_", "DJANGO_", "AICED_"))
            and key not in ("AICED_S3_PASSWORD", "AICED_S3_STATE")
        }
        (directory / "integration-env.json").write_text(json.dumps(private_env))
        (directory / "internal-keys.json").write_text(json.dumps(keys))
        (directory / "iam-env.json").write_text(
            json.dumps(
                {
                    key: value
                    for key, value in child.items()
                    if key.startswith(("POSTGRES_", "DJANGO_", "AICED_"))
                }
            )
        )
        (directory / "migration-env.json").write_text(
            json.dumps(
                {
                    **private_env,
                    "POSTGRES_USER": spec["roles"]["migrator"],
                    "POSTGRES_PASSWORD": spec["passwords"]["migrator"],
                    "AICED_MIGRATION_ROLE": spec["roles"]["owner"],
                }
            )
        )
        with ExitStack() as stack:
            iam_process = stack.enter_context(
                server(
                    "iam",
                    [
                        sys.executable,
                        "backend/manage.py",
                        "runserver",
                        f"127.0.0.1:{iam_port}",
                        "--noreload",
                        "--settings",
                        "internal_api.settings",
                    ],
                    child,
                    iam_port,
                )
            )
            stack.enter_context(
                server(
                    "backend",
                    [
                        sys.executable,
                        "backend/manage.py",
                        "runserver",
                        f"127.0.0.1:{backend_port}",
                        "--noreload",
                    ],
                    child,
                    backend_port,
                )
            )
            service = stack.enter_context(
                server(
                    "integration",
                    [
                        *command,
                        "runserver",
                        f"127.0.0.1:{integration_port}",
                        "--noreload",
                    ],
                    integration_env,
                    integration_port,
                )
            )
            stack.enter_context(
                server(
                    "frontend",
                    [
                        str(ROOT / ".tools/node.exe"),
                        str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(frontend_port),
                        "--strictPort",
                    ],
                    {**child, "API_PROXY_TARGET": f"http://127.0.0.1:{backend_port}"},
                    frontend_port,
                    cwd=ROOT / "frontend",
                )
            )
            base = stack.enter_context(
                nginx_gateway(
                    directory / "gateway",
                    f"127.0.0.1:{backend_port}",
                    f"127.0.0.1:{frontend_port}",
                    child["AICED_GATEWAY_KEY"],
                    integration=f"127.0.0.1:{integration_port}",
                )
            )
            uploader, reviewer, it = [Browser(base) for _ in range(3)]
            for browser, name in (
                (uploader, "uploader"),
                (reviewer, "reviewer"),
                (it, "it"),
            ):
                browser.login(state[name]["username"], child["AICED_S3_PASSWORD"])
            org = state["organization_id"]
            root = f"/api/imports/{org}/"
            upload = (
                root + f"upload/?template=legal&source_as_of={date.today().isoformat()}"
            )
            passed(
                "separate real IAM, legacy and Integration processes started with separate credentials through Nginx"
            )
            assert (
                Browser(base).request(
                    "/api/imports/context/",
                    headers={"X-User-ID": state["uploader"]["id"], "X-Role": "admin"},
                )[0]
                == 403
            )
            assert it.request(root + "batches/")[0] == 403
            assert (
                uploader.request(
                    f"/api/imports/{state['other_organization_id']}/batches/"
                )[0]
                == 403
            )
            context = uploader.request("/api/imports/context/")
            assert context[0] == 200 and context[1]["organizations"][0]["id"] == org
            assert context[2]["Cache-Control"] == "no-store"
            history = reviewer.request(root + f"batches/{state['batch_id']}/")
            assert (
                history[0] == 200
                and history[1]["batch"]["published_rows"] == 1
                and any(
                    event["action"] == "imports.published"
                    for event in history[1]["history"]
                )
            )
            passed(
                "forged headers, missing finance, cross-org denial, context and restored publication history"
            )
            assert (
                uploader.request(
                    upload,
                    b"broken",
                    headers={"Content-Type": "application/octet-stream"},
                )[0]
                == 400
            )
            content = workbook("S3-NEW-" + run)
            code, batch, _ = uploader.request(
                upload, content, headers={"Content-Type": "application/octet-stream"}
            )
            assert code == 201, code
            assert (
                uploader.request(
                    upload,
                    content,
                    headers={"Content-Type": "application/octet-stream"},
                )[0]
                == 200
            )
            batch_id = batch["id"]
            assert batch["rejected"] == 2
            preview = uploader.request(root + f"batches/{batch_id}/")
            assert preview[0] == 200 and preview[1]["count"] == 3
            assert uploader.request(root + f"batches/{batch_id}/rejections/")[0] == 200
            assert (
                uploader.request(
                    root + f"batches/{batch_id}/publish/",
                    {"policy_id": state["policy_id"], "skip_rejected": True},
                )[0]
                == 403
            )
            assert (
                reviewer.request(
                    root + f"batches/{batch_id}/publish/",
                    {"policy_id": state["policy_id"]},
                )[0]
                == 400
            )
            result = reviewer.request(
                root + f"batches/{batch_id}/publish/",
                {"policy_id": state["policy_id"], "skip_rejected": True},
            )
            assert result[0] == 200 and result[1]["published_rows"] == 1
            assert (
                reviewer.request(
                    root + f"batches/{batch_id}/publish/",
                    {"policy_id": state["policy_id"], "skip_rejected": True},
                )[0]
                == 200
            )
            policy = uploader.request(
                root + "policies/",
                {
                    "template": "legal",
                    "key_column": 2,
                    "rationale": "Synthetic S3 immutable snapshot policy only",
                },
            )
            assert policy[0] == 201
            assert (
                uploader.request(root + f"policies/{policy[1]['id']}/approve/", {})[0]
                == 403
            )
            assert (
                reviewer.request(root + f"policies/{policy[1]['id']}/approve/", {})[0]
                == 200
            )
            assert (
                reviewer.request(root + f"policies/{policy[1]['id']}/revoke/", {})[0]
                == 200
            )
            assert reviewer.request(root + "policies/")[0] == 200
            assert (
                uploader.request(
                    upload,
                    workbook("S3-CSRF"),
                    headers={
                        "Content-Type": "application/octet-stream",
                        "X-CSRFToken": "invalid",
                    },
                )[0]
                == 403
            )
            passed(
                "all nine import routes: XLSX errors, duplicate rows, preview/CSV, policy review/revoke, partial publication and idempotency"
            )
            (directory / "browser-synthetic.xlsx").write_bytes(
                workbook("S3-BROWSER-" + run)
            )
            execute(
                "candidate-browser",
                [str(ROOT / ".tools/node.exe"), "scripts/s3_browser.mjs"],
                {
                    **child,
                    "AICED_S3_URL": base,
                    "AICED_S3_WORKBOOK": str(directory / "browser-synthetic.xlsx"),
                    "AICED_S3_REPORT_DIR": str(directory),
                },
            )
            passed(
                "Chromium: unchanged login/import screens, restored preview, XLSX upload, rejected rows and permission-aware IT denial"
            )
            with psycopg.connect(**connection_args(admin), autocommit=True) as conn:
                counts = [
                    count(conn, table)
                    for table in (TABLES[1], TABLES[2], "integration_store_journal")
                ]
                conn.execute(
                    sql.SQL(
                        "REVOKE INSERT ON aiced_integration.integration_store_outbox FROM {}"
                    ).format(sql.Identifier(spec["roles"]["runtime"]))
                )
                try:
                    assert (
                        uploader.request(
                            upload,
                            workbook("S3-AUDIT-FAIL"),
                            headers={"Content-Type": "application/octet-stream"},
                        )[0]
                        == 500
                    )
                    assert counts == [
                        count(conn, table)
                        for table in (TABLES[1], TABLES[2], "integration_store_journal")
                    ]
                finally:
                    conn.execute(
                        sql.SQL(
                            "GRANT INSERT ON aiced_integration.integration_store_outbox TO {}"
                        ).format(sql.Identifier(spec["roles"]["runtime"]))
                    )
            passed(
                "required outbox insert failure rolls back batch, staging rows and journal atomically"
            )
            # Queue an actual HTTP import at its local organization admission.
            with runtime_connect() as lock:
                lock.execute("BEGIN")
                lock.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    (uuid.UUID(org).int % (2**63 - 1),),
                )
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        uploader.request,
                        upload,
                        workbook("S3-REVOKED-WAITER"),
                        headers={"Content-Type": "application/octet-stream"},
                    )
                    deadline = time.monotonic() + 10
                    with psycopg.connect(
                        **connection_args(admin), autocommit=True
                    ) as conn:
                        while not conn.execute(
                            "SELECT 1 FROM pg_stat_activity WHERE usename=%s AND wait_event='advisory'",
                            (spec["roles"]["runtime"],),
                        ).fetchone():
                            if time.monotonic() > deadline:
                                raise AssertionError(
                                    "Import did not wait for local admission"
                                )
                            time.sleep(0.02)
                        conn.execute(
                            "UPDATE public.identity_roleassignment SET is_active=false WHERE id=%s",
                            (state["uploader"]["assignment_id"],),
                        )
                    lock.execute("COMMIT")
                    assert future.result(timeout=10)[0] == 403
            assert uploader.request(root + "batches/")[0] == 403
            with psycopg.connect(**connection_args(admin), autocommit=True) as conn:
                conn.execute(
                    "UPDATE public.identity_roleassignment SET is_active=true WHERE id=%s",
                    (state["uploader"]["assignment_id"],),
                )
                conn.execute(
                    "UPDATE public.identity_user SET is_active=false WHERE id=%s",
                    (state["uploader"]["id"],),
                )
            assert uploader.request(root + "batches/")[0] == 403
            passed(
                "actual cross-process revocation overtakes queued write; permission change and user deactivation deny fresh access"
            )
            execute(
                "audit-delivery",
                [*command, "deliver_integration_audit", "--limit", "1000"],
                integration_env,
            )
            execute(
                "audit-delivery-idempotent",
                [*command, "deliver_integration_audit", "--limit", "1000"],
                integration_env,
            )
            with runtime_connect() as conn:
                assert (
                    conn.execute(
                        "SELECT count(*) FROM integration_store_outbox WHERE delivered_at IS NULL"
                    ).fetchone()[0]
                    == 0
                )
            passed(
                "outbox worker signs real HTTP deliveries, drains pending events and safely repeats"
            )
            iam_process.terminate()
            iam_process.wait(timeout=10)
            assert reviewer.request(root + "batches/")[0] == 503
            assert (
                reviewer.request(
                    root + f"batches/{batch_id}/publish/",
                    {"policy_id": state["policy_id"]},
                )[0]
                == 503
            )
            assert Browser(base).request("/api/imports/context/")[0] == 403
            with runtime_connect() as conn:
                pending = conn.execute(
                    "SELECT event_id FROM integration_store_outbox WHERE delivered_at IS NULL"
                ).fetchall()
                assert pending
            with (directory / "audit-offline.log").open("wb") as log:
                result = subprocess.run(
                    [*command, "deliver_integration_audit", "--limit", "1000"],
                    cwd=ROOT,
                    env=integration_env,
                    stdout=log,
                    stderr=log,
                )
                assert result.returncode != 0
            with runtime_connect() as conn:
                assert conn.execute(
                    "SELECT count(*) FROM integration_store_outbox WHERE delivered_at IS NULL AND attempts>0"
                ).fetchone()[0] >= len(pending)
            passed(
                "IAM process loss fails reads and writes closed with 503; no ORM fallback"
            )
            service.terminate()
            service.wait(timeout=10)
            assert reviewer.request(root + "batches/")[0] == 502
            assert reviewer.request("/api/session/")[0] == 200
            passed(
                "Integration process loss produces Gateway 502 while legacy session API remains available"
            )
            stack.enter_context(
                server(
                    "iam-restarted",
                    [
                        sys.executable,
                        "backend/manage.py",
                        "runserver",
                        f"127.0.0.1:{iam_port}",
                        "--noreload",
                        "--settings",
                        "internal_api.settings",
                    ],
                    child,
                    iam_port,
                )
            )
            stack.enter_context(
                server(
                    "integration-restarted",
                    [
                        *command,
                        "runserver",
                        f"127.0.0.1:{integration_port}",
                        "--noreload",
                    ],
                    integration_env,
                    integration_port,
                )
            )
            restarted = reviewer.request(root + f"batches/{batch_id}/")
            assert restarted[0] == 200 and restarted[1]["batch"]["published_rows"] == 1
            execute(
                "audit-retry",
                [*command, "deliver_integration_audit", "--limit", "1000"],
                integration_env,
            )
            passed(
                "service restart preserves published data; offline outbox remains pending and drains after IAM recovery"
            )

        # Backup and restore the owned schema AFTER candidate commits, retaining
        # owners/triggers/ACL/data. PostgreSQL DB-level TEMP ACL is separately
        # reinstated, since pg_dump without --create does not include that ACL.
        def owned_state(database):
            with psycopg.connect(**connection_args(admin, database)) as conn:
                tables = [
                    row[0]
                    for row in conn.execute(
                        "SELECT tablename FROM pg_tables WHERE schemaname=%s ORDER BY tablename",
                        (SCHEMA,),
                    )
                ]
                result = {}
                for table in tables:
                    rows = conn.execute(
                        sql.SQL(
                            "SELECT to_jsonb(t)::text FROM {}.{} t ORDER BY to_jsonb(t)::text"
                        ).format(sql.Identifier(SCHEMA), sql.Identifier(table))
                    ).fetchall()
                    result[table] = hashlib.sha256(
                        json.dumps(rows).encode()
                    ).hexdigest()
                for key, query in {
                    "constraints": "SELECT c.relname,k.conname,pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s ORDER BY 1,2",
                    "triggers": "SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND NOT t.tgisinternal ORDER BY 1,2",
                    "owners_acl": "SELECT c.relname,pg_get_userbyid(c.relowner),c.relacl::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relkind IN ('r','S') ORDER BY 1",
                }.items():
                    result[key] = [list(row) for row in conn.execute(query, (SCHEMA,))]
                for row in result["constraints"]:
                    row[2] = canonical_constraint(row[2])
                return result

        candidate_before = owned_state(env["POSTGRES_DB"])
        second = f"aiced_m1_{run}_source"
        scratch.create(second)
        candidate_backup = directory / "candidate-after-commits.dump"
        admin_pg = [
            "--host",
            admin["POSTGRES_HOST"],
            "--port",
            str(admin["POSTGRES_PORT"]),
            "--username",
            admin["POSTGRES_USER"],
        ]
        admin_env = {**child, "PGPASSWORD": admin["POSTGRES_PASSWORD"]}
        execute(
            "candidate-backup",
            [
                pg_binary("pg_dump"),
                *admin_pg,
                "--format=custom",
                "--file",
                str(candidate_backup),
                "--dbname",
                env["POSTGRES_DB"],
            ],
            admin_env,
        )
        execute(
            "candidate-restore",
            [
                pg_binary("pg_restore"),
                *admin_pg,
                "--exit-on-error",
                "--dbname",
                second,
                str(candidate_backup),
            ],
            admin_env,
        )
        require_equal(
            candidate_before,
            owned_state(second),
            "Owned schema post-commit restore parity",
        )
        with psycopg.connect(**connection_args(admin, second), autocommit=True) as conn:
            conn.execute(
                sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(second)
                )
            )
        restore_runtime = {**integration_env, "POSTGRES_DB": second}
        execute(
            "candidate-restored-check",
            [*command, "showmigrations", "--plan"],
            restore_runtime,
        )
        with server(
            "restored-integration",
            [*command, "runserver", f"127.0.0.1:{integration_port}", "--noreload"],
            restore_runtime,
            integration_port,
        ):
            assert (
                Browser(f"http://127.0.0.1:{integration_port}").request(
                    "/api/imports/context/"
                )[0]
                == 403
            )
        passed(
            "post-commit candidate backup/restore: exact owned records, constraints, triggers, owners/ACL and separate-process startup"
        )
        scratch.drop(second)
        # Rollback candidate routing against the untouched legacy dataset.
        with ExitStack() as stack:
            stack.enter_context(
                server(
                    "rollback-backend",
                    [
                        sys.executable,
                        "backend/manage.py",
                        "runserver",
                        f"127.0.0.1:{backend_port}",
                        "--noreload",
                    ],
                    child,
                    backend_port,
                )
            )
            base = stack.enter_context(
                nginx_gateway(
                    directory / "rollback-gateway",
                    f"127.0.0.1:{backend_port}",
                    f"127.0.0.1:{backend_port}",
                    child["AICED_GATEWAY_KEY"],
                )
            )
            browser = Browser(base)
            browser.login(state["reviewer"]["username"], child["AICED_S3_PASSWORD"])
            assert browser.request(root + f"batches/{state['batch_id']}/")[0] == 200
        passed(
            "pre-cutover rollback: default Gateway imports route still serves original history"
        )
        report["status"] = "passed"
    finally:
        try:
            require_equal(
                before, fingerprint(original), "Existing application stayed unchanged"
            )
            report["existing_database_unchanged"] = True
            if not (options.keep_candidate and report["status"] == "passed"):
                for name in list(scratch.created):
                    scratch.drop(name)
                if spec:
                    with psycopg.connect(
                        **connection_args(admin, "postgres"), autocommit=True
                    ) as conn:
                        cleanup_roles(conn, env, spec)
                report["scratch_removed"] = True
        finally:
            if report["status"] != "passed":
                report["status"] = "failed"
            save()
            print("Private S3 report: " + str(directory / "report.json"), flush=True)


if __name__ == "__main__":
    main()
