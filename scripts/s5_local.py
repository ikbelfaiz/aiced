"""Controlled S5 portable-local cutover. Production and remote databases refused."""

import argparse, hashlib, json, os, socket, subprocess, sys, time, uuid, secrets
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
)
from s5_backup import backup_restore


def validate(env):
    if (
        env.get("POSTGRES_DB") != "aiced"
        or env.get("POSTGRES_HOST") != "127.0.0.1"
        or str(env.get("POSTGRES_PORT")) != "55432"
        or env.get("DJANGO_DEBUG") != "1"
    ):
        raise ValueError(
            "Only the existing portable synthetic local deployment is allowed"
        )


def write(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2))
    temp.replace(path)


def stop(directory):
    config = json.loads((directory / "deployment.json").read_text())
    (directory / "stop").write_text("S5 coordinated stop")
    deadline = time.monotonic() + 40
    while True:
        live = []
        for name in [
            "backend_port",
            "iam_port",
            "integration_port",
            "frontend_port",
            "gateway_port",
            *(["commercial_port"] if config.get("commercial_port") else []),
        ]:
            try:
                with socket.create_connection(("127.0.0.1", config[name]), timeout=0.1):
                    live.append(name)
            except OSError:
                pass
        if not live:
            return
        if time.monotonic() > deadline:
            raise RuntimeError("Deployment did not stop; no transfer performed")
        time.sleep(0.25)


def start(directory):
    # Windows hidden detached launch, no secrets in command arguments or console.
    command = subprocess.list2cmdline(
        ["scripts/run_s4_deployment.py", "--directory", str(directory)]
    )
    ps = (
        "Start-Process -FilePath '"
        + sys.executable.replace("'", "''")
        + "' -ArgumentList '"
        + command.replace("'", "''")
        + "' -WorkingDirectory '"
        + str(ROOT).replace("'", "''")
        + "' -WindowStyle Hidden"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True
    )


def execute(directory, label, args, env):
    with (directory / (label + ".log")).open("wb") as log:
        subprocess.run(
            args,
            cwd=ROOT,
            env={**os.environ, **env, "PYTHONPATH": str(ROOT / ".tools/python")},
            stdout=log,
            stderr=log,
            check=True,
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--confirm-local-cutover", action="store_true", required=True)
    p.add_argument("--verification-report", type=Path)
    p.add_argument("--rollback", action="store_true")
    p.add_argument("--forward", action="store_true")
    args = p.parse_args()
    directory = args.directory.resolve()
    if (
        not directory.is_relative_to(ROOT / ".local/s4-active")
        or not (directory / "deployment.json").is_file()
    ):
        raise ValueError("Only marked existing S4 local deployment directory accepted")
    if json.loads((directory / "deployment.json").read_text()).get("mode") != "service":
        raise ValueError(
            "Restore the verified S4 Integration service before an S5 operation"
        )
    if args.rollback and args.forward:
        raise ValueError("Choose only one direction")
    s6state = directory / "s6-state.json"
    if s6state.exists() and json.loads(s6state.read_text()).get("writer") == "service":
        raise ValueError("Roll back S6 Commercial before changing S5 IAM ownership")
    originalfile = directory / "s5-legacy-backend-env.json"
    env = json.loads(
        (
            originalfile if originalfile.exists() else directory / "backend-env.json"
        ).read_text()
    )
    validate(env)
    admin = {
        **env,
        "POSTGRES_USER": "aiced_owner",
        "POSTGRES_PASSWORD": json.loads(
            (ROOT / ".local/postgres/credentials.json").read_text()
        )["owner"],
    }
    statepath = directory / "s5-state.json"
    if args.rollback or args.forward:
        state = json.loads(statepath.read_text())
        if state.get('status') not in ('configured','active_verified','rollback_verified'):
            raise ValueError('Incomplete preparation/switch requires reviewed recovery; writers remain stopped')

        spec = json.loads((directory / "s5-ownership-private.json").read_text())
        mode = "legacy" if args.rollback else "service"
        if state["writer"] == mode:
            raise ValueError("Writer already active; no switch required")
    else:
        if statepath.exists():
            raise ValueError("S5 already prepared; use explicit rollback/forward")
        if not args.verification_report:
            raise ValueError("Passing disposable rehearsal required")
        proof = json.loads(args.verification_report.read_text())
        if (
            proof.get("status") != "passed"
            or not proof.get("original_unchanged")
            or not proof.get("final_backup", {}).get("restoration_verified")
        ):
            raise ValueError("Incomplete S5 rehearsal")
        for name, digest in proof["code_hashes"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                raise ValueError("Code differs from passing rehearsal: " + name)
        with psycopg.connect(**connection_args(admin), autocommit=True) as c:
            if c.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname='aiced_iam'"
            ).fetchone():
                raise ValueError(
                    "Existing IAM schema requires explicit reviewed recovery"
                )
        state = {
            "run": uuid.uuid4().hex,
            "writer": "legacy",
            "status": "preparing",
            "rehearsal": str(args.verification_report),
            "backups": [],
        }
        write(originalfile, env)
        write(
            directory / "s5-legacy-integration-env.json",
            json.loads((directory / "integration-env.json").read_text()),
        )
        write(
            directory / "s5-legacy-deployment.json",
            json.loads((directory / "deployment.json").read_text()),
        )
        mode = "service"
    stamp = uuid.uuid4().hex[:10]
    state["backups"].append(
        backup_restore(env, admin, directory, "s5-" + stamp + "-pre-stop")
    )
    write(statepath, state)
    stop(directory)
    state["status"] = "stopped"
    write(statepath, state)
    try:
        state["backups"].append(
            backup_restore(env, admin, directory, "s5-" + stamp + "-stopped")
        )
        write(statepath, state)
        if not (args.rollback or args.forward):

            def localguard(conn, checkenv):
                validate(checkenv)
                if conn.execute("SELECT current_database()").fetchone() != ("aiced",):
                    raise ValueError("Wrong database")

            with psycopg.connect(**connection_args(admin), autocommit=True) as c:
                spec = provision(
                    c, {**env, "AICED_REHEARSAL_RUN": state["run"]}, verify=localguard
                )
            write(directory / "s5-ownership-private.json", spec)
            migrator = {
                **env,
                "POSTGRES_USER": spec["roles"]["migrator"],
                "POSTGRES_PASSWORD": spec["passwords"]["migrator"],
                "AICED_MIGRATION_ROLE": spec["roles"]["owner"],
            }
            write(directory / "iam-migration-env.json", migrator)
            execute(
                directory,
                "s5-iam-migrate",
                [
                    sys.executable,
                    "backend/iam_service/manage.py",
                    "migrate",
                    "--noinput",
                ],
                migrator,
            )
            offline = {**env, "AICED_CONSUMER_MIGRATION": "1"}
            execute(
                directory,
                "s5-refs-migrate",
                [
                    sys.executable,
                    "backend/manage.py",
                    "migrate",
                    "iam_consumer",
                    "--noinput",
                    "--settings",
                    "iam_consumer.settings",
                ],
                offline,
            )
            with psycopg.connect(**connection_args(admin), autocommit=True) as c:
                refs(c)
                c.execute(
                    sql.SQL("TRUNCATE {} CASCADE").format(
                        sql.SQL(",").join(
                            sql.SQL("aiced_iam.{}").format(sql.Identifier(t))
                            for t in BASE
                        )
                    )
                )
            execute(
                directory,
                "s5-consumer-migrate",
                [
                    sys.executable,
                    "backend/manage.py",
                    "migrate",
                    "--noinput",
                    "--settings",
                    "iam_consumer.settings",
                ],
                offline,
            )
            with psycopg.connect(**connection_args(admin), autocommit=True) as c:
                transfer(c, "forward")
                grants(c, spec)
                fence(c, spec, env["POSTGRES_USER"])
                activate(c, "service")
            keys = json.loads(env["AICED_INTERNAL_KEYS"])
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
            iamenv = {
                **env,
                "POSTGRES_USER": spec["roles"]["runtime"],
                "POSTGRES_PASSWORD": spec["passwords"]["runtime"],
                "AICED_INTERNAL_KEYS": json.dumps(
                    {k: v for k, v in keys.items() if k != "client-integration-v1"}
                ),
            }
            config = json.loads((directory / "deployment.json").read_text())
            consumer = {
                **env,
                "POSTGRES_USER": spec["roles"]["consumer"],
                "POSTGRES_PASSWORD": spec["passwords"]["consumer"],
                "DJANGO_SECRET_KEY": secrets.token_urlsafe(48),
                "AICED_INTERNAL_KEYS": json.dumps(
                    {k: keys[k] for k in ["client-iam-v1", "client-integration-v1"]}
                ),
                "AICED_IAM_URL": f"http://127.0.0.1:{config['iam_port']}",
                "AICED_INTEGRATION_AUDIT_KEY_ID": "client-integration-v1",
            }
            integration = json.loads((directory / "integration-env.json").read_text())
            integration["AICED_INTERNAL_KEYS"] = json.dumps(
                {
                    **json.loads(integration["AICED_INTERNAL_KEYS"]),
                    "client-integration-v1": keys["client-integration-v1"],
                }
            )
            for name, value in [
                ("s5-service-iam-env", iamenv),
                ("s5-service-consumer-env", consumer),
                ("s5-service-integration-env", integration),
            ]:
                write(directory / (name + ".json"), value)
        else:
            with psycopg.connect(**connection_args(admin), autocommit=True) as c:
                freeze(c)
                if mode == "legacy":
                    transfer(c, "reverse")
                    retarget(c, False)
                    fence(c, spec, env["POSTGRES_USER"], False)
                else:
                    refs(c)
                    transfer(c, "forward")
                    retarget(c, True)
                    fence(c, spec, env["POSTGRES_USER"])
                activate(c, mode)
        if mode == "service":
            write(
                directory / "backend-env.json",
                json.loads((directory / "s5-service-consumer-env.json").read_text()),
            )
            write(
                directory / "iam-env.json",
                json.loads((directory / "s5-service-iam-env.json").read_text()),
            )
            write(
                directory / "integration-env.json",
                json.loads((directory / "s5-service-integration-env.json").read_text()),
            )
        else:
            legacy = {
                **env,
                "AICED_INTERNAL_KEYS": json.loads(
                    (directory / "s5-service-iam-env.json").read_text()
                )["AICED_INTERNAL_KEYS"],
            }
            write(directory / "backend-env.json", legacy)
            write(directory / "iam-env.json", legacy)
            write(
                directory / "integration-env.json",
                json.loads((directory / "s5-legacy-integration-env.json").read_text()),
            )
        config = json.loads((directory / "deployment.json").read_text())
        config.update(
            backend_settings=(
                "iam_consumer.settings" if mode == "service" else "config.settings"
            ),
            iam_settings=(
                "iam_service.settings"
                if mode == "service"
                else "iam_service.legacy_settings"
            ),
            iam_routing=True,
        )
        write(directory / "deployment.json", config)
        state.update(writer=mode, status="configured")
        write(statepath, state)
        start(directory)
        print(
            "S5 local deployment started; verify Gateway and record state before acceptance.",
            flush=True,
        )
    except Exception:
        state["status"] = "failed_stopped"
        write(statepath, state)
        # Do not blindly restart stale credentials/writers after an ownership failure.
        raise


if __name__ == "__main__":
    main()
