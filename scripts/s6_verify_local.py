"""Verify the real local S6 writer; no production environment accepted."""

import argparse, json, sys, time, subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / ".tools/python"),
    str(ROOT / "backend"),
    str(ROOT / "scripts"),
]
import psycopg, yaml
from migration_baseline import connection_args
from s5_local import validate, write
from s3_rehearsal import Browser


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--phase", choices=["initial", "rollback", "final"], required=True)
    args = p.parse_args()
    directory = args.directory.resolve()
    if not directory.is_relative_to(ROOT / ".local/s4-active"):
        raise ValueError("Unmarked local directory")
    client = json.loads((directory / "backend-env.json").read_text())
    validate(client)
    state = json.loads((directory / "s6-state.json").read_text())
    mode = "legacy" if args.phase == "rollback" else "service"
    if state.get("writer") != mode:
        raise ValueError("Wrong writer for verification phase")
    config = json.loads((directory / "deployment.json").read_text())
    url = f"http://127.0.0.1:{config['gateway_port']}"
    browser = Browser(url)
    until = time.monotonic() + 35
    while True:
        try:
            if browser.request("/api/health/")[0] == 200:
                break
        except OSError:
            pass
        if time.monotonic() > until:
            raise RuntimeError("Gateway unavailable")
        time.sleep(0.3)
    password = (ROOT / ".local/postgres/seed-password").read_text().strip()
    browser.login("synthetic.operator.a", password)
    admin = {
        **client,
        "POSTGRES_USER": "aiced_owner",
        "POSTGRES_PASSWORD": json.loads(
            (ROOT / ".local/postgres/credentials.json").read_text()
        )["owner"],
    }

    def connect(e=admin):
        return psycopg.connect(**connection_args(e), autocommit=True)

    evidencepath = directory / "s6-active-verification.json"
    evidence = json.loads(evidencepath.read_text()) if evidencepath.exists() else {}
    if args.phase == "initial":
        with connect() as c:
            party, org = c.execute(
                "SELECT p.id,p.organization_id FROM public.clients_party p JOIN aiced_iam.identity_organization o ON o.id=p.organization_id WHERE o.code='SYNTHETIC-A' AND NOT EXISTS(SELECT 1 FROM public.clients_prospect x WHERE x.party_id=p.id) ORDER BY p.id LIMIT 1"
            ).fetchone()
            original_count = c.execute(
                "SELECT count(*) FROM public.clients_opportunity"
            ).fetchone()[0]
        base = f"/api/clients/{party}/opportunities/"
        status, row, _ = browser.request(
            base, {"title": "S6 active synthetic opportunity", "amount": "654.321"}
        )
        assert status == 201, (status, row)
        assert (
            browser.request(
                base + row["id"] + "/",
                {"version": 1, "title": "S6 active verified"},
                method="PATCH",
            )[0]
            == 200
        )
        evidence.update(
            party_id=str(party),
            organization_id=str(org),
            item_id=row["id"],
            archive_initial_count=original_count,
        )
        with connect() as c:
            assert (
                c.execute("SELECT count(*) FROM public.clients_opportunity").fetchone()[
                    0
                ]
                == original_count
            )
            assert c.execute(
                "SELECT amount,version,title FROM aiced_commercial.clients_opportunity WHERE id=%s",
                [row["id"]],
            ).fetchone()[1:] == (2, "S6 active verified")
    else:
        base = f"/api/clients/{evidence['party_id']}/opportunities/"
        result = browser.request(base + evidence["item_id"] + "/")
        assert (
            result[0] == 200
            and result[1]["version"] == 2
            and result[1]["amount"] == "654.321"
            and result[1]["title"] == "S6 active verified"
        ), result
        if args.phase == "rollback":
            status, row, _ = browser.request(
                base, {"title": "S6 new legacy synthetic write", "amount": "777.777"}
            )
            assert status == 201, (status, row)
            evidence["legacy_item_id"] = row["id"]
        else:
            row = browser.request(base + evidence["legacy_item_id"] + "/")
            assert (
                row[0] == 200
                and row[1]["amount"] == "777.777"
                and row[1]["title"] == "S6 new legacy synthetic write"
            ), row
    schema = browser.request("/api/schema/?format=json")
    assert schema[0] == 200 and schema[1] == yaml.safe_load(
        (
            ROOT
            / ".local/migration-baseline/ad738f3cd11047e290efb80b12af1bc2/openapi.yaml"
        ).read_text(encoding="utf-8")
    )
    for username in ["synthetic.it.a", "synthetic.reader.b"]:
        denied = Browser(url)
        denied.login(username, password)
        assert denied.request(base)[0] == 404
    assert (
        Browser(url).request(base, headers={"X-User": "admin", "X-Role": "superuser"})[
            0
        ]
        == 403
    )
    auditor = Browser(url)
    auditor.login("synthetic.manager.a", password)
    assert auditor.request("/api/audit/")[0] == 200
    if mode == "service":
        commercial = json.loads((directory / "commercial-env.json").read_text())
        with connect(commercial) as c:
            for table in [
                "public.clients_party",
                "public.clients_financialaccount",
                "public.clients_opportunity",
                "aiced_iam.identity_user",
                "aiced_integration.ingestion_importbatch",
            ]:
                for verb in [
                    "SELECT * FROM " + table + " LIMIT 0",
                    "DELETE FROM " + table + " WHERE false",
                ]:
                    try:
                        c.execute(verb)
                    except psycopg.errors.InsufficientPrivilege:
                        pass
                    else:
                        raise AssertionError("Foreign access allowed")
        with connect(client) as c:
            try:
                c.execute("SELECT * FROM aiced_commercial.clients_opportunity LIMIT 0")
            except psycopg.errors.InsufficientPrivilege:
                pass
            else:
                raise AssertionError("Client accesses Commercial")
        with connect() as c:
            assert not c.execute(
                "SELECT 1 FROM pg_constraint k JOIN pg_class r ON r.oid=k.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace JOIN pg_class t ON t.oid=k.confrelid JOIN pg_namespace d ON d.oid=t.relnamespace WHERE k.contype='f' AND n.nspname='aiced_commercial' AND d.nspname<>'aiced_commercial'"
            ).fetchone()
        processes = json.loads((directory / "process-status.json").read_text())
        assert all(
            processes[n]["running"]
            for n in ["backend", "iam", "commercial", "integration"]
        )
        evidence["processes"] = processes
    evidence[args.phase] = {
        "passed": True,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "writer": mode,
    }
    write(evidencepath, evidence)
    state["status"] = "rollback_verified" if mode == "legacy" else "active_verified"
    state["verified_at"] = datetime.now(timezone.utc).isoformat()
    write(directory / "s6-state.json", state)
    print(
        "S6 active phase verified:",
        args.phase,
        "; public OpenAPI, authorization, stored data and owned-schema checks passed.",
    )


if __name__ == "__main__":
    main()
