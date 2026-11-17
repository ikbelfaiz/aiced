"""S6 restored-database gate. Never changes active ownership or runtime credentials."""

import argparse, json, os, secrets, subprocess, sys, time, uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / ".tools/python"),
    str(ROOT / "backend"),
    str(ROOT / "scripts"),
]
import psycopg
from psycopg import sql
from migration_baseline import ScratchDatabases, connection_args, pg_binary
from s5_backup import apply_database_acl
from s6_backup import backup_restore, snapshot
from s6_database import provision, grants, transfer, freeze, activate, fence
from s5_rehearsal import server
from s3_rehearsal import Browser
from testing.gateway import free_port, nginx_gateway
from internal_api.client import InternalClient


def connect(env):
    return psycopg.connect(**connection_args(env), autocommit=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-local-rehearsal", required=True, action="store_true")
    parser.add_argument("--keep-candidate", action="store_true")
    args = parser.parse_args()
    active = ROOT / ".local/s4-active/b1cb997fda7f49a4a6331979c656bfb6"
    source = json.loads((active / "backend-env.json").read_text())
    if (
        source.get("POSTGRES_DB") != "aiced"
        or source.get("POSTGRES_HOST") != "127.0.0.1"
        or str(source.get("POSTGRES_PORT")) != "55432"
        or source.get("DJANGO_DEBUG") != "1"
    ):
        raise ValueError("Local synthetic deployment only")
    admin = {
        **source,
        "POSTGRES_USER": "aiced_owner",
        "POSTGRES_PASSWORD": json.loads(
            (ROOT / ".local/postgres/credentials.json").read_text()
        )["owner"],
    }
    run = uuid.uuid4().hex
    directory = ROOT / ".local/s6b-rehearsal" / run
    directory.mkdir(parents=True)
    env = {
        **source,
        "POSTGRES_DB": f"aiced_m1_{run}_restore",
        "AICED_REHEARSAL_RUN": run,
    }
    admenv = {**admin, "POSTGRES_DB": env["POSTGRES_DB"]}
    scratch = ScratchDatabases(
        {
            **env,
            "POSTGRES_USER": admin["POSTGRES_USER"],
            "POSTGRES_PASSWORD": admin["POSTGRES_PASSWORD"],
        },
        source["POSTGRES_DB"],
    )
    report = {"status": "running", "checks": [], "active_ownership_modified": False}
    with connect(admin) as c:
        c.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        before = snapshot(c)
        c.execute("ROLLBACK")

    def passed(name):
        report["checks"].append(name)
        print(name, flush=True)

    def save(name, value):
        (directory / (name + ".json")).write_text(
            json.dumps(value, indent=2, default=str)
        )

    def execute(label, command, child):
        with (directory / (label + ".log")).open("wb") as log:
            p = subprocess.run(
                [sys.executable, *command],
                cwd=ROOT,
                env={**os.environ, **child, "PYTHONPATH": str(ROOT / ".tools/python")},
                stdout=log,
                stderr=log,
            )
        if p.returncode:
            raise RuntimeError(label + " failed; inspect private log")

    from s6_local import manifest

    starting_manifest = manifest()
    spec = None
    try:
        proof = backup_restore(admin, admin, directory, "before-ownership")
        passed(
            "Current full backup independently restored and catalog/data/ACL parity verified before DDL"
        )
        scratch.create(env["POSTGRES_DB"])
        with (directory / "restore.log").open("wb") as log:
            subprocess.run(
                [
                    pg_binary("pg_restore"),
                    "--host",
                    admin["POSTGRES_HOST"],
                    "--port",
                    str(admin["POSTGRES_PORT"]),
                    "--username",
                    admin["POSTGRES_USER"],
                    "--exit-on-error",
                    "--dbname",
                    env["POSTGRES_DB"],
                    proof["backup"],
                ],
                env={**os.environ, **admin, "PGPASSWORD": admin["POSTGRES_PASSWORD"]},
                stdout=log,
                stderr=log,
                check=True,
            )
        apply_database_acl(admin, env["POSTGRES_DB"], before["database_acl"])
        execute(
            "client-preparation-migrate",
            [
                "backend/manage.py",
                "migrate",
                "--noinput",
                "--settings",
                "iam_consumer.settings",
            ],
            {**admenv, "AICED_CONSUMER_MIGRATION": "1"},
        )
        with connect(admenv) as c:
            spec = provision(c, env)
            c.execute(
                sql.SQL(
                    "GRANT SELECT,INSERT ON public.iam_consumer_commercialjournalref TO {}"
                ).format(sql.Identifier(source["POSTGRES_USER"]))
            )
        save("ownership-private", spec)
        keys = {
            k: {
                "secret": secrets.token_urlsafe(48),
                "service": service,
                "audiences": audiences,
            }
            for k, service, audiences in [
                ("commercial-iam-v1", "commercial", ["iam", "audit"]),
                ("commercial-client-v1", "commercial", ["client"]),
                ("client-commercial-v1", "client_crm", ["commercial"]),
            ]
        }
        ports = {
            name: free_port()
            for name in ["iam", "client", "commercial", "integration", "frontend"]
        }
        iam = {
            **json.loads((active / "iam-env.json").read_text()),
            "POSTGRES_DB": env["POSTGRES_DB"],
            "LOGIN_ACCOUNT_LIMIT": "1000",
            "LOGIN_IP_LIMIT": "2000",
        }
        iam["AICED_INTERNAL_KEYS"] = json.dumps(
            {
                **json.loads(iam["AICED_INTERNAL_KEYS"]),
                "commercial-iam-v1": keys["commercial-iam-v1"],
            }
        )
        client = {
            **env,
            "AICED_IAM_URL": f"http://127.0.0.1:{ports['iam']}",
            "AICED_COMMERCIAL_URL": f"http://127.0.0.1:{ports['commercial']}",
            "AICED_COMMERCIAL_AUDIT_KEY_ID": "client-commercial-v1",
            "AICED_COMMERCIAL_REMOTE": "1",
            "AICED_INTEGRATION_AUDIT_URL": f"http://127.0.0.1:{ports['integration']}",
        }
        client["AICED_INTERNAL_KEYS"] = json.dumps(
            {
                **json.loads(client["AICED_INTERNAL_KEYS"]),
                **{
                    k: keys[k] for k in ["commercial-client-v1", "client-commercial-v1"]
                },
            }
        )
        integration = {
            **json.loads((active / "integration-env.json").read_text()),
            "POSTGRES_DB": env["POSTGRES_DB"],
            "AICED_IAM_URL": client["AICED_IAM_URL"],
        }
        commercial = {
            **env,
            "POSTGRES_USER": spec["roles"]["runtime"],
            "POSTGRES_PASSWORD": spec["passwords"]["runtime"],
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(48),
            "AICED_INTERNAL_KEYS": json.dumps(keys),
            "AICED_IAM_URL": client["AICED_IAM_URL"],
            "AICED_CLIENT_URL": f"http://127.0.0.1:{ports['client']}",
        }
        migrator = {
            **commercial,
            "POSTGRES_USER": spec["roles"]["migrator"],
            "POSTGRES_PASSWORD": spec["passwords"]["migrator"],
            "AICED_MIGRATION_ROLE": spec["roles"]["owner"],
        }
        execute(
            "commercial-migrate",
            ["backend/commercial_service/manage.py", "migrate", "--noinput"],
            migrator,
        )
        execute(
            "commercial-check",
            ["backend/commercial_service/manage.py", "check"],
            migrator,
        )
        execute(
            "commercial-migration-drift",
            [
                "backend/commercial_service/manage.py",
                "makemigrations",
                "--check",
                "--dry-run",
            ],
            migrator,
        )
        with connect(admenv) as c:
            grants(c, spec)
            with c.transaction():
                transfer(c, "forward")
                fence(c, spec, source["POSTGRES_USER"], True)
                activate(c, "service")
        save("ownership-private", spec)
        for name, value in [
            ("iam-env", iam),
            ("client-env", client),
            ("integration-env", integration),
            ("commercial-env", commercial),
            ("migration-env", migrator),
        ]:
            save(name, value)
        passed(
            "Separate Commercial migration lineage, exact forward transfer and old SQL writer fencing verified on restored data"
        )
        # Effective SQL role checks use real LOGIN credentials, not SET ROLE.
        for other in [
            "public.clients_party",
            "public.clients_financialaccount",
            "public.clients_opportunity",
            "aiced_iam.identity_user",
            "aiced_integration.ingestion_importbatch",
        ]:
            with connect(commercial) as c:
                for statement in [
                    f"SELECT * FROM {other} LIMIT 0",
                    f"DELETE FROM {other} WHERE false",
                ]:
                    try:
                        c.execute(statement)
                    except psycopg.errors.InsufficientPrivilege:
                        pass
                    else:
                        raise AssertionError(
                            "Commercial cross-schema access: " + statement
                        )
        with connect(client) as c:
            for table in [
                "public.clients_opportunity",
                "aiced_commercial.clients_opportunity",
            ]:
                try:
                    c.execute(f"SELECT * FROM {table} LIMIT 0")
                except psycopg.errors.InsufficientPrivilege:
                    pass
                else:
                    raise AssertionError("Client can read Commercial/archive table")
        passed(
            "Actual LOGIN credentials deny Commercial foreign reads/writes and Client reads of owned/archived opportunities"
        )
        execute(
            "commercial-isolated-tests",
            [
                "backend/commercial_service/manage.py",
                "test",
                "commercial_service",
                "--noinput",
            ],
            commercial,
        )
        with ExitStack() as stack:
            processes = {}
            for name, child, settings in [
                ("iam", iam, "iam_service.settings"),
                ("client", client, "iam_consumer.settings"),
                ("integration", integration, "integration_service.settings"),
                ("commercial", commercial, "commercial_service.settings"),
            ]:
                processes[name] = stack.enter_context(
                    server(
                        directory,
                        name,
                        [
                            sys.executable,
                            "backend/manage.py",
                            "runserver",
                            f"127.0.0.1:{ports[name]}",
                            "--noreload",
                            "--settings",
                            settings,
                        ],
                        child,
                        ports[name],
                    )
                )
            processes["frontend"] = stack.enter_context(
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
                        str(ports["frontend"]),
                        "--strictPort",
                    ],
                    client,
                    ports["frontend"],
                )
            )
            url = stack.enter_context(
                nginx_gateway(
                    directory / "gateway",
                    f"127.0.0.1:{ports['client']}",
                    f"127.0.0.1:{ports['frontend']}",
                    client["AICED_GATEWAY_KEY"],
                    iam=f"127.0.0.1:{ports['iam']}",
                    integration=f"127.0.0.1:{ports['integration']}",
                    commercial=f"127.0.0.1:{ports['commercial']}",
                )
            )
            report["processes"] = {
                name: {"pid": p.pid, "port": ports[name], "running": p.poll() is None}
                for name, p in processes.items()
            }
            browser = Browser(url)
            password = (ROOT / ".local/postgres/seed-password").read_text().strip()
            browser.login("synthetic.operator.a", password)
            with connect(admenv) as c:
                actor = c.execute(
                    "SELECT id FROM aiced_iam.identity_user WHERE username='synthetic.operator.a'"
                ).fetchone()[0]
                party, org = c.execute(
                    "SELECT p.id,p.organization_id FROM public.clients_party p JOIN aiced_iam.identity_organization o ON o.id=p.organization_id WHERE o.code='SYNTHETIC-A' AND NOT EXISTS(SELECT 1 FROM public.clients_prospect x WHERE x.party_id=p.id) ORDER BY p.id LIMIT 1"
                ).fetchone()
            base = f"/api/clients/{party}/opportunities/"
            status, data, _ = browser.request(
                base, {"title": "S6 independent synthetic", "amount": "123.456"}
            )
            assert status == 201, (status, data)
            item = data["id"]
            assert data["amount"] == "123.456"
            assert (
                browser.request(
                    base + item + "/",
                    {"version": 1, "title": "S6 updated"},
                    method="PATCH",
                )[0]
                == 200
            )
            assert (
                browser.request(
                    base + item + "/", {"version": 1, "title": "Stale"}, method="PATCH"
                )[0]
                == 409
            )
            assert (
                browser.request(
                    base + item + "/",
                    {"version": 2, "author_id": str(actor)},
                    method="PATCH",
                )[0]
                == 400
            )
            assert browser.request(base + item + "/")[1]["title"] == "S6 updated"
            auditor = Browser(url)
            auditor.login("synthetic.manager.a", password)
            assert auditor.request("/api/audit/")[0] == 200
            execute(
                "commercial-outbox-delivery",
                [
                    "backend/commercial_service/manage.py",
                    "deliver_commercial_audit",
                    "--limit",
                    "100",
                ],
                commercial,
            )
            with connect(admenv) as c:
                receipt_count = c.execute(
                    "SELECT count(*) FROM aiced_iam.audit_auditreceipt WHERE producer='commercial'"
                ).fetchone()[0]
                event = c.execute(
                    "SELECT event_id FROM aiced_commercial.commercial_store_outbox WHERE delivered_at IS NOT NULL LIMIT 1"
                ).fetchone()[0]
                c.execute(
                    "UPDATE aiced_commercial.commercial_store_outbox SET delivered_at=NULL WHERE event_id=%s",
                    [event],
                )
            execute(
                "commercial-outbox-retry",
                [
                    "backend/commercial_service/manage.py",
                    "deliver_commercial_audit",
                    "--limit",
                    "100",
                ],
                commercial,
            )
            with connect(admenv) as c:
                assert (
                    c.execute(
                        "SELECT count(*) FROM aiced_iam.audit_auditreceipt WHERE producer='commercial'"
                    ).fetchone()[0]
                    == receipt_count
                )

            passed(
                "Signed Commercial outbox delivery and repeat delivery are accepted idempotently by IAM"
            )

            assert (
                Browser(url).request(
                    base, headers={"X-User": str(actor), "X-Role": "admin"}
                )[0]
                == 403
            )
            passed(
                "Four independent Django processes: real Gateway authentication, exact Decimal, CRUD, stale/duplicate PATCH, strict fields, forged role headers and federated audit"
            )
            from s6_probes import run as concurrency_probes

            concurrency_probes(
                admenv,
                client,
                commercial,
                iam,
                browser,
                actor,
                party,
                org,
                item,
                passed,
            )
            # Stop only one child at a time, proving there is no restart dependency.
            original_pids = {name: p.pid for name, p in processes.items()}

            def restart(name, child, settings):
                processes[name].terminate()
                processes[name].wait(timeout=10)
                processes[name] = stack.enter_context(
                    server(
                        directory,
                        name + "-restart",
                        [
                            sys.executable,
                            "backend/manage.py",
                            "runserver",
                            f"127.0.0.1:{ports[name]}",
                            "--noreload",
                            "--settings",
                            settings,
                        ],
                        child,
                        ports[name],
                    )
                )

            processes["client"].terminate()
            processes["client"].wait(timeout=10)
            with connect(admenv) as c:
                before_count = c.execute(
                    "SELECT count(*) FROM aiced_commercial.clients_opportunity"
                ).fetchone()[0]
            assert browser.request(base, {"title": "S6 unavailable Client"})[0] == 503
            with connect(admenv) as c:
                assert (
                    before_count
                    == c.execute(
                        "SELECT count(*) FROM aiced_commercial.clients_opportunity"
                    ).fetchone()[0]
                )
            processes["client"] = stack.enter_context(
                server(
                    directory,
                    "client-restart",
                    [
                        sys.executable,
                        "backend/manage.py",
                        "runserver",
                        f"127.0.0.1:{ports['client']}",
                        "--noreload",
                        "--settings",
                        "iam_consumer.settings",
                    ],
                    client,
                    ports["client"],
                )
            )
            assert browser.request(base + item + "/")[0] == 200
            restart("commercial", commercial, "commercial_service.settings")
            assert browser.request(base + item + "/")[0] == 200
            assert (
                processes["iam"].pid == original_pids["iam"]
                and processes["integration"].pid == original_pids["integration"]
            )
            processes["iam"].terminate()
            processes["iam"].wait(timeout=10)
            assert browser.request(base)[0] == 503
            processes["iam"] = stack.enter_context(
                server(
                    directory,
                    "iam-restart",
                    [
                        sys.executable,
                        "backend/manage.py",
                        "runserver",
                        f"127.0.0.1:{ports['iam']}",
                        "--noreload",
                        "--settings",
                        "iam_service.settings",
                    ],
                    iam,
                    ports["iam"],
                )
            )
            assert browser.request(base + item + "/")[0] == 200
            report["restarted_processes"] = {
                name: p.pid for name, p in processes.items()
            }
            passed(
                "Independent Client/Commercial/IAM restarts preserve sessions; Client/IAM outages fail closed without new opportunities"
            )
            # Session deletion is managed only by IAM and is visible immediately.
            with connect(iam) as c:
                session = next(
                    cookie.value for cookie in browser.jar if cookie.name == "sessionid"
                )
                c.execute(
                    "DELETE FROM aiced_iam.django_session WHERE session_key=%s",
                    [session],
                )
            assert browser.request(base)[0] == 403
            browser.login("synthetic.operator.a", password)
            assert browser.request(base)[0] == 200
            passed(
                "Revoked session denied across service processes; explicit new login restores access"
            )
            import yaml

            schema = browser.request("/api/schema/?format=json")
            assert schema[0] == 200
            from contracts.additions import assert_openapi_compatible
            assert_openapi_compatible(schema[1],yaml.safe_load(
                (
                    ROOT
                    / ".local/migration-baseline/ad738f3cd11047e290efb80b12af1bc2/openapi.yaml"
                ).read_text(encoding="utf-8")
            ))
            passed(
                "Entire public OpenAPI equals frozen baseline through four-service Gateway"
            )

            def fresh_browser_workbook():
                import openpyxl
                from ingestion.templates import TEMPLATES

                book = openpyxl.Workbook()
                sheet = book.active
                sheet.title = TEMPLATES["legal"]["sheet"]
                sheet.append(TEMPLATES["legal"]["headers"])
                for value in ("S6-" + uuid.uuid4().hex, "S6-DUP", "S6-DUP"):
                    row = [None] * 25
                    row[1] = value
                    row[3] = "SOCIETE SYNTHETIQUE S6"
                    row[4] = "13/02/2026"
                    sheet.append(row)
                target = ROOT / ".local/ui-review/synthetic-legal.xlsx"
                target.parent.mkdir(parents=True, exist_ok=True)
                book.save(target)

            fresh_browser_workbook()
            browser_env = {
                **os.environ,
                "AICED_E2E_URL": url,
                "AICED_E2E_PASSWORD": password,
                "AICED_E2E_REPORT_DIR": str(directory / "browser"),
                "PATH": str(ROOT / ".tools") + os.pathsep + os.environ.get("PATH", ""),
            }
            with (directory / "browser.log").open("wb") as log:
                result = subprocess.run(
                    [
                        str(ROOT / ".tools/node.exe"),
                        str(ROOT / "frontend/node_modules/@playwright/test/cli.js"),
                        "test",
                        "--timeout",
                        "60000",
                        "--grep-invert",
                        "production build",
                    ],
                    cwd=ROOT / "frontend",
                    env=browser_env,
                    stdout=log,
                    stderr=log,
                )
            if result.returncode:
                raise RuntimeError(
                    "Four-service browser workflow failure; inspect private browser report"
                )
            passed(
                "All development Chromium workflows pass against four independently running services"
            )

            previewport = free_port()
            for label, command in [
                (
                    "frontend-typecheck",
                    [
                        str(ROOT / ".tools/node.exe"),
                        str(ROOT / "frontend/node_modules/typescript/bin/tsc"),
                        "--noEmit",
                        "--project",
                        str(ROOT / "frontend/tsconfig.json"),
                    ],
                ),
                (
                    "frontend-build",
                    [
                        str(ROOT / ".tools/node.exe"),
                        str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                        "build",
                        str(ROOT / "frontend"),
                    ],
                ),
            ]:
                with (directory / (label + ".log")).open("wb") as log:
                    subprocess.run(
                        command,
                        cwd=ROOT,
                        env=browser_env,
                        stdout=log,
                        stderr=log,
                        check=True,
                    )
            stack.enter_context(
                server(
                    directory,
                    "frontend-compiled",
                    [
                        str(ROOT / ".tools/node.exe"),
                        str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                        "preview",
                        str(ROOT / "frontend"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(previewport),
                        "--strictPort",
                    ],
                    client,
                    previewport,
                )
            )
            fresh_browser_workbook()
            compiled_url = stack.enter_context(
                nginx_gateway(
                    directory / "gateway-compiled",
                    f"127.0.0.1:{ports['client']}",
                    f"127.0.0.1:{previewport}",
                    client["AICED_GATEWAY_KEY"],
                    iam=f"127.0.0.1:{ports['iam']}",
                    integration=f"127.0.0.1:{ports['integration']}",
                    commercial=f"127.0.0.1:{ports['commercial']}",
                )
            )
            with (directory / "browser-compiled.log").open("wb") as log:
                result = subprocess.run(
                    [
                        str(ROOT / ".tools/node.exe"),
                        str(ROOT / "frontend/node_modules/@playwright/test/cli.js"),
                        "test",
                        "--timeout",
                        "60000",
                        "--grep",
                        "production build|Client 360|Data Management|Prospects",
                    ],
                    cwd=ROOT / "frontend",
                    env={
                        **browser_env,
                        "AICED_E2E_URL": compiled_url,
                        "AICED_E2E_PRODUCTION": "1",
                        "AICED_E2E_REPORT_DIR": str(directory / "browser-compiled"),
                    },
                    stdout=log,
                    stderr=log,
                )
            if result.returncode:
                raise RuntimeError("Compiled four-service browser workflow failure")
            passed(
                "TypeScript/build and all compiled Chromium workflows pass through the four-service Gateway"
            )
            # Copy back all new writes while listeners stopped before ownership changes.
        with connect(admenv) as c:
            freeze(c)
            with c.transaction():
                transfer(c, "reverse")
                fence(c, spec, source["POSTGRES_USER"], False)
                activate(c, "legacy")
        passed(
            "Post-write reverse transfer retains every new opportunity version, actor, journal and outbox"
        )
        legacy = {**client, "AICED_COMMERCIAL_REMOTE": "0"}
        with ExitStack() as stack:
            stack.enter_context(
                server(
                    directory,
                    "rollback-iam",
                    [
                        sys.executable,
                        "backend/manage.py",
                        "runserver",
                        f"127.0.0.1:{ports['iam']}",
                        "--noreload",
                        "--settings",
                        "iam_service.settings",
                    ],
                    iam,
                    ports["iam"],
                )
            )
            stack.enter_context(
                server(
                    directory,
                    "rollback-client",
                    [
                        sys.executable,
                        "backend/manage.py",
                        "runserver",
                        f"127.0.0.1:{ports['client']}",
                        "--noreload",
                        "--settings",
                        "iam_consumer.settings",
                    ],
                    legacy,
                    ports["client"],
                )
            )
            url = stack.enter_context(
                nginx_gateway(
                    directory / "rollback-gateway",
                    f"127.0.0.1:{ports['client']}",
                    f"127.0.0.1:{ports['client']}",
                    client["AICED_GATEWAY_KEY"],
                    iam=f"127.0.0.1:{ports['iam']}",
                )
            )
            b = Browser(url)
            b.login("synthetic.operator.a", password)
            assert (
                b.request(base + item + "/")[1]["title"]
                == "S6 admitted before scope change"
            )
            status, legacy_item, _ = b.request(
                base, {"title": "S6 rollback new legacy write"}
            )
            assert status == 201, (status, legacy_item)
        with connect(admenv) as c:
            freeze(c)
            with c.transaction():
                transfer(c, "forward")
                fence(c, spec, source["POSTGRES_USER"], True)
                activate(c, "service")
            assert (
                c.execute(
                    "SELECT title FROM aiced_commercial.clients_opportunity WHERE id=%s",
                    [legacy_item["id"]],
                ).fetchone()[0]
                == "S6 rollback new legacy write"
            )
        passed(
            "Legacy write after rollback survives forward transfer with exact table parity"
        )
        backup_restore(admenv, admenv, directory, "after-forward")
        passed(
            "New Commercial tables, data, sequences, triggers, credentials and ACLs survive full backup/restore"
        )
        report["status"] = "verified-candidate"
        if manifest() != starting_manifest:
            raise RuntimeError(
                "Source changed during rehearsal; repeat against stable source"
            )
        report["source_manifest"] = starting_manifest
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        raise
    finally:
        with connect(admin) as c:
            c.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            after = snapshot(c)
            c.execute("ROLLBACK")
        report["active_data_catalog_acl_unchanged"] = before == after
        if before != after:
            report["status"] = "failed"
            report["error"] = (
                "Active snapshot changed during rehearsal; review before cutover"
            )
        if not (args.keep_candidate and report["status"] != "failed"):
            for db in list(scratch.created):
                scratch.drop(db)
        report["candidate_retained"] = bool(scratch.created)
        save("report", report)
        print("Private report:", directory / "report.json", flush=True)


if __name__ == "__main__":
    main()
