"""Portable-local S6 cutover only, after exact current-source restored rehearsal."""

import argparse, hashlib, json, os, secrets, sys, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / ".tools/python"),
    str(ROOT / "scripts"),
    str(ROOT / "backend"),
]
import psycopg
from migration_baseline import connection_args
from s5_local import validate, write, stop, start, execute
from s6_backup import backup_restore
from s6_database import provision, grants, transfer, freeze, activate, fence
from psycopg import sql


def manifest():
    files = [
        *ROOT.glob("backend/**/*.py"),
        *ROOT.glob("scripts/*.py"),
        *ROOT.glob("infra/gateway/*"),
        *ROOT.glob("compose*.yaml"),
        *ROOT.glob("backend/Dockerfile*"),
    ]
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(files)
        if p.is_file()
    }


def guard_active(conn, env):
    validate(env)
    if conn.execute("SELECT current_database()").fetchone()[0] != "aiced":
        raise ValueError("Unexpected active DB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--confirm-local-cutover", action="store_true", required=True)
    parser.add_argument("--verification-report", type=Path)
    directions = parser.add_mutually_exclusive_group()
    directions.add_argument("--rollback", action="store_true")
    directions.add_argument("--forward", action="store_true")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if (
        not directory.is_relative_to(ROOT / ".local/s4-active")
        or not (directory / "deployment.json").is_file()
    ):
        raise ValueError("Unmarked active directory")
    if json.loads((directory / "s5-state.json").read_text()).get("writer") != "service":
        raise ValueError("IAM S5 must remain service-owned")
    config = json.loads((directory / "deployment.json").read_text())
    if config.get("mode") != "service":
        raise ValueError("Integration must remain service-owned")
    statepath = directory / "s6-state.json"
    env = json.loads((directory / "backend-env.json").read_text())
    validate(env)
    admin = {
        **env,
        "POSTGRES_USER": "aiced_owner",
        "POSTGRES_PASSWORD": json.loads(
            (ROOT / ".local/postgres/credentials.json").read_text()
        )["owner"],
    }

    def connect():
        return psycopg.connect(**connection_args(admin), autocommit=True)

    if args.rollback or args.forward:
        state = json.loads(statepath.read_text())
        if state["status"] not in (
            "configured",
            "active_verified",
            "rollback_verified",
        ):
            raise ValueError("Incomplete transition; reviewed recovery required")
        mode = "legacy" if args.rollback else "service"
        if state["writer"] == mode:
            raise ValueError("Writer is already " + mode)
        spec = json.loads((directory / "s6-ownership-private.json").read_text())
    else:
        if statepath.exists() or not args.verification_report:
            raise ValueError("Fresh cutover requires a passed restored rehearsal")
        reportpath = args.verification_report.resolve()
        if not reportpath.is_relative_to(ROOT / ".local/s6b-rehearsal"):
            raise ValueError("Untrusted rehearsal path")
        report = json.loads(reportpath.read_text())
        if (
            report.get("status") != "verified-candidate"
            or report.get("active_data_catalog_acl_unchanged") is not True
            or report.get("source_manifest") != manifest()
        ):
            raise ValueError("Current-source restored rehearsal has not passed")
        with connect() as c:
            if c.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname='aiced_commercial'"
            ).fetchone():
                raise ValueError("Existing Commercial schema; no automatic retry")
        state = {
            "run": uuid.uuid4().hex,
            "status": "preparing",
            "writer": "legacy",
            "rehearsal": str(reportpath),
            "backups": [],
        }
        mode = "service"
        spec = None
        for name in ["backend-env", "iam-env", "integration-env", "deployment"]:
            write(
                directory / ("s6-legacy-" + name + ".json"),
                json.loads((directory / (name + ".json")).read_text()),
            )
    label = (
        "s6-"
        + ("rollback" if args.rollback else "forward" if args.forward else "initial")
        + "-"
        + uuid.uuid4().hex[:10]
    )
    state["backups"].append(backup_restore(admin, admin, directory, label + "-live"))
    write(statepath, state)
    stop(directory)
    # Any failure from here deliberately leaves all writers stopped.
    state["status"] = "stopped"
    write(statepath, state)
    state["backups"].append(backup_restore(admin, admin, directory, label + "-stopped"))
    if spec is None:
        runenv = {**env, "AICED_REHEARSAL_RUN": state["run"]}
        with connect() as c:
            spec = provision(c, runenv, verify=guard_active)
        keys = {
            ident: {
                "secret": secrets.token_urlsafe(48),
                "service": service,
                "audiences": audiences,
            }
            for ident, service, audiences in [
                ("commercial-iam-v1", "commercial", ["iam", "audit"]),
                ("commercial-client-v1", "commercial", ["client"]),
                ("client-commercial-v1", "client_crm", ["commercial"]),
            ]
        }
        iam = json.loads((directory / "s6-legacy-iam-env.json").read_text())
        iam["AICED_INTERNAL_KEYS"] = json.dumps(
            {
                **json.loads(iam["AICED_INTERNAL_KEYS"]),
                "commercial-iam-v1": keys["commercial-iam-v1"],
            }
        )
        client = json.loads((directory / "s6-legacy-backend-env.json").read_text())
        client.update(
            AICED_COMMERCIAL_REMOTE="1",
            AICED_COMMERCIAL_URL="http://127.0.0.1:8004",
            AICED_COMMERCIAL_AUDIT_KEY_ID="client-commercial-v1",
        )
        client["AICED_INTERNAL_KEYS"] = json.dumps(
            {
                **json.loads(client["AICED_INTERNAL_KEYS"]),
                **{
                    k: keys[k] for k in ["commercial-client-v1", "client-commercial-v1"]
                },
            }
        )
        commercial = {
            **client,
            "POSTGRES_USER": spec["roles"]["runtime"],
            "POSTGRES_PASSWORD": spec["passwords"]["runtime"],
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(48),
            "AICED_INTERNAL_KEYS": json.dumps(keys),
            "AICED_IAM_URL": client["AICED_IAM_URL"],
            "AICED_CLIENT_URL": "http://127.0.0.1:8000",
        }
        migrator = {
            **commercial,
            "POSTGRES_USER": spec["roles"]["migrator"],
            "POSTGRES_PASSWORD": spec["passwords"]["migrator"],
            "AICED_MIGRATION_ROLE": spec["roles"]["owner"],
        }
        write(directory / "s6-ownership-private.json", spec)
        write(directory / "commercial-migration-env.json", migrator)
        execute(
            directory,
            "s6-client-migrate",
            [
                sys.executable,
                "backend/manage.py",
                "migrate",
                "--noinput",
                "--settings",
                "iam_consumer.settings",
            ],
            {**admin, "AICED_CONSUMER_MIGRATION": "1"},
        )
        execute(
            directory,
            "s6-commercial-migrate",
            [
                sys.executable,
                "backend/commercial_service/manage.py",
                "migrate",
                "--noinput",
            ],
            migrator,
        )
        with connect() as c:
            grants(c, spec)
            c.execute(
                sql.SQL(
                    "GRANT SELECT,INSERT ON public.iam_consumer_commercialjournalref TO {}"
                ).format(sql.Identifier(client["POSTGRES_USER"]))
            )
        for name, value in [
            ("iam", iam),
            ("client", client),
            ("commercial", commercial),
        ]:
            write(directory / ("s6-service-" + name + "-env.json"), value)
    with connect() as c:
        freeze(c)
        with c.transaction():
            transfer(c, "reverse" if mode == "legacy" else "forward")
            fence(c, spec, env["POSTGRES_USER"], mode == "service")
            activate(c, mode)
    write(directory / "s6-ownership-private.json", spec)
    if mode == "service":
        for name, target in [
            ("iam", "iam"),
            ("client", "backend"),
            ("commercial", "commercial"),
        ]:
            write(
                directory / (target + "-env.json"),
                json.loads(
                    (directory / ("s6-service-" + name + "-env.json")).read_text()
                ),
            )
        config = json.loads((directory / "s6-legacy-deployment.json").read_text())
        config.update(commercial_port=8004, commercial_routing=True)
    else:
        for name in ["backend-env", "iam-env", "integration-env"]:
            write(
                directory / (name + ".json"),
                json.loads((directory / ("s6-legacy-" + name + ".json")).read_text()),
            )
        config = json.loads((directory / "s6-legacy-deployment.json").read_text())
    write(directory / "deployment.json", config)
    state.update(status="configured", writer=mode)
    write(statepath, state)
    start(directory)
    print(
        "S6 writer configured:",
        mode,
        "; run the independent HTTP/data verification before marking verified.",
        flush=True,
    )


if __name__ == "__main__":
    main()
