"""Real HTTP/SQL concurrency probes, only inside an already marked S6 restore."""

import copy, json, time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from uuid import UUID
import psycopg
from migration_baseline import connection_args
from internal_api.security import signed_headers
from s3_rehearsal import Browser

BARRIER = 4711239301896721
SCOPE = 591445740000006


def connect(env):
    return psycopg.connect(**connection_args(env), autocommit=True)


def clone(browser):
    b = Browser(browser.base)
    for cookie in browser.jar:
        b.jar.set_cookie(copy.copy(cookie))
    return b


def waiting(admin, role, needle, timeout=3):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        with connect(admin) as c:
            if c.execute(
                "SELECT 1 FROM pg_stat_activity WHERE usename=%s AND wait_event_type='Lock' AND query ILIKE %s",
                [role, "%" + needle + "%"],
            ).fetchone():
                return
        time.sleep(0.025)
    raise AssertionError("Expected database wait: " + needle)


def run(admin, client, commercial, iam, browser, actor, party, org, item, passed):
    base = f"/api/clients/{party}/opportunities/"
    with connect(admin) as c:
        member = c.execute(
            "SELECT id FROM aiced_iam.identity_membership WHERE user_id=%s AND organization_id=%s",
            [actor, org],
        ).fetchone()[0]
        other = c.execute(
            "SELECT id FROM public.iam_consumer_membershipref WHERE organization_id=%s AND id<>%s LIMIT 1",
            [org, member],
        ).fetchone()[0]
        original_assigned = c.execute(
            "SELECT assigned_to_id FROM public.clients_party WHERE id=%s", [party]
        ).fetchone()[0]
        assignments = c.execute(
            "SELECT id,scope FROM aiced_iam.identity_roleassignment WHERE membership_id=%s",
            [member],
        ).fetchall()
        c.execute(
            "UPDATE aiced_iam.identity_roleassignment SET scope='assigned' WHERE membership_id=%s",
            [member],
        )
        c.execute(
            "UPDATE public.clients_party SET assigned_to_id=%s WHERE id=%s",
            [member, party],
        )

    with connect(client) as c:
        for statement, values in [
            ("DELETE FROM public.clients_party WHERE id=%s", [party]),
            (
                "UPDATE public.clients_party SET id=%s WHERE id=%s",
                [UUID(int=123), party],
            ),
            (
                "UPDATE public.clients_party SET organization_id=%s WHERE id=%s",
                [UUID(int=456), party],
            ),
        ]:
            try:
                c.execute(statement, values)
            except psycopg.errors.CheckViolation:
                pass
            else:
                raise AssertionError(
                    "Client runtime can destroy or rekey a remote reference"
                )
    passed(
        "Client runtime cannot delete/rekey/reparent referenced parties; source identity references remain stable"
    )

    def count():
        with connect(commercial) as c:
            return c.execute(
                "SELECT count(*) FROM aiced_commercial.clients_opportunity"
            ).fetchone()[0]

    def version():
        with connect(commercial) as c:
            return c.execute(
                "SELECT version FROM aiced_commercial.clients_opportunity WHERE id=%s",
                [item],
            ).fetchone()[0]

    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            # Client classification/assignment wins admission before Commercial check.
            before = count()
            with connect(client) as c:
                c.execute("BEGIN")
                c.execute(
                    "UPDATE public.clients_party SET assigned_to_id=%s WHERE id=%s",
                    [other, party],
                )
                future = pool.submit(
                    clone(browser).request, base, {"title": "S6 forbidden queued write"}
                )
                waiting(
                    admin, commercial["POSTGRES_USER"], "pg_advisory_xact_lock_shared"
                )
                assert not future.done()
                c.execute("COMMIT")
                assert future.result(timeout=10)[0] == 404
            assert count() == before
            with connect(client) as c:
                c.execute(
                    "UPDATE public.clients_party SET assigned_to_id=%s WHERE id=%s",
                    [member, party],
                )
            passed(
                "Client reassignment overtakes queued Commercial write: fresh object scope denies 404, no mutation"
            )
            # Reproduce the S6a deadlock cycle with an org row locked by a queued Client writer.
            with connect(commercial) as comm:
                comm.execute("BEGIN")
                comm.execute("SELECT pg_advisory_xact_lock_shared(%s)", [BARRIER])
                comm.execute("SELECT pg_advisory_xact_lock_shared(%s)", [SCOPE])

                def change():
                    with connect(client) as c:
                        c.execute("BEGIN")
                        c.execute(
                            "SELECT id FROM public.iam_consumer_organizationref WHERE id=%s FOR UPDATE",
                            [org],
                        )
                        c.execute(
                            "UPDATE public.clients_party SET assigned_to_id=%s WHERE id=%s",
                            [member, party],
                        )
                        c.execute("COMMIT")

                pending = pool.submit(change)
                waiting(admin, client["POSTGRES_USER"], "UPDATE public.clients_party")
                credentials = {
                    "session_key": next(
                        c.value for c in browser.jar if c.name == "sessionid"
                    ),
                    "method": "GET",
                    "host": browser.base.split("://")[1],
                    "scheme": "http",
                }
                path = "/internal/v1/clients/authorize"
                body = json.dumps(
                    {
                        "credentials": credentials,
                        "party_id": str(party),
                        "capability": "opportunities.view",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                key = json.loads(commercial["AICED_INTERNAL_KEYS"])[
                    "commercial-client-v1"
                ]
                headers = signed_headers(
                    "commercial-client-v1", key["secret"], "client", path, body
                )

                def raw(h):
                    try:
                        r = urlopen(
                            Request(
                                commercial["AICED_CLIENT_URL"] + path,
                                data=body,
                                headers=h,
                            ),
                            timeout=3,
                        )
                    except HTTPError as e:
                        r = e
                    return r.status, r.read()

                assert (
                    raw(headers)[0] == 200
                )  # Must not update/lock Client actor/org references.
                assert raw(headers)[0] == 403  # Committed replay record.
                forged = {**headers, "X-Aiced-Nonce": "a" * 48}
                assert raw(forged)[0] == 403
                wrong = signed_headers(
                    "commercial-client-v1", key["secret"], "iam", path, body
                )
                assert raw(wrong)[0] == 403
                comm.execute("COMMIT")
                pending.result(timeout=5)
            passed(
                "Stateless signed Client authorization succeeds while Client writer holds org row; forgery/audience/replay rejected"
            )
            # Commercial already admitted; Client changes must wait through commit.
            with connect(admin) as lock:
                lock.execute("BEGIN")
                lock.execute(
                    "SELECT id FROM aiced_commercial.clients_opportunity WHERE id=%s FOR UPDATE",
                    [item],
                )
                current = version()
                patch = pool.submit(
                    clone(browser).request,
                    base + item + "/",
                    {"version": current, "title": "S6 admitted before scope change"},
                    "PATCH",
                )
                waiting(admin, commercial["POSTGRES_USER"], "FOR UPDATE")

                def reassign():
                    with connect(client) as c:
                        c.execute(
                            "UPDATE public.clients_party SET assigned_to_id=%s WHERE id=%s",
                            [other, party],
                        )

                changed = pool.submit(reassign)
                waiting(admin, client["POSTGRES_USER"], "UPDATE public.clients_party")
                assert not changed.done()
                lock.execute("COMMIT")
                assert patch.result(timeout=10)[0] == 200
                changed.result(timeout=5)
            assert browser.request(base)[0] == 404
            with connect(client) as c:
                c.execute(
                    "UPDATE public.clients_party SET assigned_to_id=%s WHERE id=%s",
                    [member, party],
                )
            passed(
                "Admitted Commercial update commits before conflicting Client assignment; later access denied"
            )
            # Revocation wins ahead of a waiting write. Authorization is refreshed after barrier.
            before = count()
            with connect(admin) as c:
                c.execute("BEGIN")
                c.execute("SELECT pg_advisory_xact_lock(%s)", [BARRIER])
                future = pool.submit(
                    clone(browser).request, base, {"title": "S6 revoked queued write"}
                )
                waiting(
                    admin, commercial["POSTGRES_USER"], "pg_advisory_xact_lock_shared"
                )
                c.execute(
                    "UPDATE aiced_iam.identity_user SET is_active=false WHERE id=%s",
                    [actor],
                )
                c.execute("COMMIT")
                assert future.result(timeout=10)[0] == 403
            assert count() == before
            with connect(iam) as c:
                c.execute(
                    "UPDATE aiced_iam.identity_user SET is_active=true WHERE id=%s",
                    [actor],
                )
            passed(
                "User deactivation overtakes queued write; fresh IAM validation denies without mutation"
            )
            # Permission change is visible immediately; no grant cache.
            with connect(admin) as c:
                workspace = c.execute(
                    "SELECT a.id FROM aiced_iam.identity_roleassignment a JOIN aiced_iam.identity_role r ON r.id=a.role_id WHERE a.membership_id=%s AND r.code='synthetic-workspace-operator'",
                    [member],
                ).fetchone()[0]
                c.execute(
                    "UPDATE aiced_iam.identity_roleassignment SET is_active=false WHERE id=%s",
                    [workspace],
                )
            assert browser.request(base, {"title": "S6 forbidden permission"})[0] == 404
            with connect(admin) as c:
                c.execute(
                    "UPDATE aiced_iam.identity_roleassignment SET is_active=true WHERE id=%s",
                    [workspace],
                )
            passed(
                "Role assignment revocation denies next operation without stale grants"
            )
            # Classification change must fence Commercial even through direct SQL.
            with connect(admin) as c:
                prospect_grants = c.execute(
                    "SELECT a.id FROM aiced_iam.identity_roleassignment a JOIN aiced_iam.identity_role r ON r.id=a.role_id WHERE a.membership_id=%s AND r.code='synthetic-prospects' AND a.is_active",
                    [member],
                ).fetchall()
                for (grant,) in prospect_grants:
                    c.execute(
                        "UPDATE aiced_iam.identity_roleassignment SET is_active=false WHERE id=%s",
                        [grant],
                    )
                classified = c.execute(
                    "SELECT 1 FROM public.clients_prospect WHERE party_id=%s", [party]
                ).fetchone()
            if classified:
                raise AssertionError(
                    "Choose a non-prospect fixture for classification test"
                )
            try:
                before = count()
                with connect(client) as c:
                    c.execute("BEGIN")
                    c.execute(
                        "INSERT INTO public.clients_prospect(party_id,source,status,next_action,next_action_date,version,updated_at) VALUES(%s,'S6 synthetic','contact','',NULL,1,now())",
                        [party],
                    )
                    pending = pool.submit(
                        clone(browser).request, base, {"title": "S6 hidden prospect"}
                    )
                    waiting(
                        admin,
                        commercial["POSTGRES_USER"],
                        "pg_advisory_xact_lock_shared",
                    )
                    c.execute("COMMIT")
                    assert pending.result(timeout=10)[0] == 404
                assert count() == before
            finally:
                with connect(admin) as c:
                    c.execute(
                        "DELETE FROM public.clients_prospect WHERE party_id=%s", [party]
                    )
                    for (grant,) in prospect_grants:
                        c.execute(
                            "UPDATE aiced_iam.identity_roleassignment SET is_active=true WHERE id=%s",
                            [grant],
                        )
            passed(
                "Prospect classification overtakes queued write and enforces missing prospects.view on the same Client object"
            )
            # Required audit insert failure must undo both creation and update.
            with connect(admin) as c:
                c.execute(
                    "CREATE FUNCTION aiced_commercial.s6_fail_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='clients.opportunities_saved' THEN RAISE EXCEPTION 'Synthetic required audit failure'; END IF; RETURN NEW; END $$"
                )
                c.execute(
                    "CREATE TRIGGER s6_fail_audit BEFORE INSERT ON aiced_commercial.commercial_store_journal FOR EACH ROW EXECUTE FUNCTION aiced_commercial.s6_fail_audit()"
                )
            try:
                before = count()
                current = version()
                assert (
                    browser.request(base, {"title": "S6 audit must roll back"})[0]
                    == 500
                )
                assert count() == before
                assert (
                    browser.request(
                        base + item + "/",
                        {"version": current, "title": "S6 audit update rollback"},
                        method="PATCH",
                    )[0]
                    == 500
                )
                assert version() == current
            finally:
                with connect(admin) as c:
                    c.execute(
                        "DROP TRIGGER s6_fail_audit ON aiced_commercial.commercial_store_journal"
                    )
                    c.execute("DROP FUNCTION aiced_commercial.s6_fail_audit()")
            passed(
                "Real required journal failure rolls back Opportunity creation and update/version"
            )
            with connect(admin) as c:
                before_journal = c.execute(
                    "SELECT count(*) FROM aiced_commercial.commercial_store_journal"
                ).fetchone()[0]
                before = count()
                c.execute(
                    "CREATE FUNCTION aiced_commercial.s6_fail_outbox() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Synthetic outbox failure'; END $$"
                )
                c.execute(
                    "CREATE TRIGGER s6_fail_outbox BEFORE INSERT ON aiced_commercial.commercial_store_outbox FOR EACH ROW EXECUTE FUNCTION aiced_commercial.s6_fail_outbox()"
                )
            try:
                assert browser.request(base, {"title": "S6 outbox rollback"})[0] == 500
                assert count() == before
                with connect(admin) as c:
                    assert (
                        c.execute(
                            "SELECT count(*) FROM aiced_commercial.commercial_store_journal"
                        ).fetchone()[0]
                        == before_journal
                    )
            finally:
                with connect(admin) as c:
                    c.execute(
                        "DROP TRIGGER s6_fail_outbox ON aiced_commercial.commercial_store_outbox"
                    )
                    c.execute("DROP FUNCTION aiced_commercial.s6_fail_outbox()")
            passed(
                "Outbox insertion failure rolls back both opportunity and required journal"
            )
    finally:
        with connect(admin) as c:
            c.execute(
                "UPDATE aiced_iam.identity_user SET is_active=true WHERE id=%s", [actor]
            )
            c.execute(
                "UPDATE public.clients_party SET assigned_to_id=%s WHERE id=%s",
                [original_assigned, party],
            )
            for ident, scope in assignments:
                c.execute(
                    "UPDATE aiced_iam.identity_roleassignment SET scope=%s WHERE id=%s",
                    [scope, ident],
                )
