# S7 — Docker Compose integration

> S8 naming update: operational filenames in this guide use the [purpose-based mapping](../docker-compose.md). Reported milestone results are historical; original inventory JSON files retain their captured filenames.

**Status: S7 verified on the disposable synthetic Docker stack.**
Production readiness and completion of the remaining business features are not
claimed. Architectural extraction stops at the existing four Django services.

Acceptance uses `compose.yaml` alone, never the historical Compose overlays.
The application consists of React, Nginx, IAM, Client & CRM, Commercial,
Data Integration and PostgreSQL. `initialize` is an offline one-shot deployment
job, not another application service. Four Django containers use independent
entry points, credentials, schemas and migration recorders. The Client schema
remains `public`, preserving S6b lineage and inaccessible historical tables.

## Reproduce on a fresh disposable environment

```powershell
python scripts/compose_prepare.py
docker compose -f compose.yaml build
docker compose -f compose.yaml up -d --wait --wait-timeout 180
docker compose -f compose.yaml ps --all
docker compose -f compose.yaml run --rm --no-deps initialize python /s7/regression.py
docker compose -f compose.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml run --rm --no-deps initialize python /s7/imports.py
docker compose -f compose.yaml run --rm --no-deps initialize python /s7/routes.py
python scripts/compose_browser.py
python scripts/compose_recovery.py
python scripts/compose_inventory.py
```

Open <http://127.0.0.1:5187>. Credentials are generated into excluded
`.local/s7/config.json`; they are never printed by these commands.
`s7_prepare.py` refuses to replace existing credentials. The frozen OpenAPI
reference is copied from the existing private M1 acceptance artifact; this is
an API definition, not a database export. If absent, provide the reviewed frozen
schema as `.local/s7/openapi-baseline.yaml` before `verify.py`; do not generate a
new expected schema from the candidate under test.

For the development-only visual-preview regression, keep every application
backend in Docker and replace only the frontend command:

```powershell
docker compose -f compose.yaml -f compose.dev.yaml up -d --no-deps frontend
docker compose -f compose.yaml restart gateway
python scripts/compose_browser.py --development
docker compose -f compose.yaml up -d --no-deps frontend
docker compose -f compose.yaml restart gateway
```

The preview-only screenshot test explicitly skips compiled builds, which
correctly exclude fictional design-preview data. The production-preview denial
test skips development builds. All applicable assertions remain intact.

## Actual acceptance results — 15 November 2026

Docker Engine **29.9.3** and Compose **v5.7.0** were available. Images were built
and the application actually executed in Docker Desktop's Linux engine.

| Gate | Observed result |
|---|---|
| Application containers | PostgreSQL, IAM, Client, Integration, Commercial, React and Nginx healthy; initialization exited 0 |
| Existing regression/contracts | **139 passed**, including actual Nginx consumer/transport contracts, on a separate Docker test database |
| Independent service suites | IAM **5**, Integration **8**, Commercial **5** passed |
| Chromium through Compose Nginx | **11 development + 11 compiled passed**, one mode-specific test skipped in each run; **0 final failures** |
| Build/static checks | Docker image builds, TypeScript/Vite production build, Python compilation, Compose validation and `git diff --check` passed |
| Four-service HTTP/SQL probes | **15 checks passed**: TLS RPC, scope/revocation races, replay/forgery/audience denial, exact Decimal, optimistic conflict, audit/outbox rollback and receipt deduplication |
| Imports | **5 checks passed**: XLSX/rejections/CSV, upload replay, two-actor review, immutable publication and publication replay |
| Public compatibility | Full frozen OpenAPI object equal; **38 public patterns / 47 method-path pairs** exercised through Nginx with public/unauthenticated denial contracts; functional methods also covered by browser and contract suites |
| SQL boundary | Four actual LOGIN users deny foreign SELECT/DELETE; privileged role flags absent; four migration histories; runtime containers have no migrator identity |
| Outages/restarts | IAM, Client, Commercial, Integration and PostgreSQL loss tested; dependent writes rejected, sessions/opportunity retained after recovery; audit refuses partial results |
| Sessions | Real gateway logout, server expiration, session deletion revocation and authorization revocation verified |
| Backup/restore | Fresh stopped-writer dump restored to separate disposable DB; **81 tables** have matching complete row digests/counts; effective database/schema/table/sequence and column ACLs match |
| Legacy independence | Runtime entry points inspected: four distinct owned-service processes; no monolithic runtime or host upstream; direct retired IAM/Commercial paths on Client deny access |

Initial startup failures and test-harness expectation errors were corrected and
rerun. In particular, logout's frozen status is 204, the schema endpoint requires
authentication, and owner-only ACLs may be encoded implicitly by PostgreSQL.
Outage/session checks passed as a complete run; the final backup gate was rerun
separately with `s7_backup.py` after correcting ACL comparison. Failed attempts
are not counted as successful checks. Final totals: **157 backend tests and 22
applicable browser executions passed**, in addition to the integration, route,
isolation, outage and restore gates above. The final running frontend serves the
compiled build at <http://127.0.0.1:5187>.

Changes are contained in `compose.s7*.yaml`, the two S7 Dockerfiles, the S7 Vite
configuration, `infra/s7/*.py`, `scripts/s7_*.py`, gateway startup/temp-directory
configuration, shell line-ending attributes, the browser test's mode guard and
these functional/operational documents. No business model, public API, historical
migration, source connector or service boundary was changed.

## Initialization and security

- Dedicated project `aiced-s7`, database `aiced_s7_disposable`, named volume
  `aiced-s7_s7_database`; no connection to or copy of the portable local database.
  Only existing synthetic seed commands run. Carthago has no network adapter or
  write path enabled.
- PostgreSQL has no published port. Only Nginx publishes loopback port 5187.
  Container-to-container addresses use Docker DNS. Private RPCs use verified TLS,
  per-service certificates and the existing scoped, distinct signing identities.
  Runtime TLS mounts contain only that service's key/certificate and public CA.
- Administrator credentials and migrator identities belong to the one-shot job;
  runtime containers receive only their own restricted LOGIN credentials. Owner
  roles remain NOLOGIN; runtime roles have no privileged flags or memberships.
- Fresh historical migrations are applied offline, then existing extraction
  operations establish service boundaries. No legacy WSGI server starts during
  initialization. Separate migration histories are retained. An incomplete
  initialization refuses automatic repair. Existing initialized volumes are
  retained without reseeding; this bootstrap is not a production upgrade tool.
- `service_completed_successfully` prevents IAM startup before initialization;
  subsequent services wait for health checks. Database locks, revocation fences,
  committed nonces and atomic journal/outbox behavior remain the S6b protocol.
- Gateway strict mode requires explicit IAM/Commercial/Integration destinations
  distinct from Client. There is no fallback server, retry or host-process route.
  The compiled frontend's acceptance configuration contains no API proxy.

## Evidence and scope

Private logs/reports are under `.local/s7/`: build logs, four regression logs,
`regression-report.json`, `integration-report.json`, `import-report.json`,
`routes-report.json`, browser reports and `recovery-report.json`.
Only sanitized results belong in Git. HTTP/SQL probes hit the real Compose
gateway and real runtime credentials. Existing Django regression suites run
inside a separate ephemeral test container against a separate Docker test DB;
their in-process fixtures and temporary contract server are regression tests,
not evidence of four-service operation. The latter is supplied by the actual
gateway/browser, signed TLS, outage and SQL-isolation probes.

The recovery runner stops only this project, never the local development DB.
It restores a fresh custom-format backup into `aiced_s7_restore`, refuses an
existing restore target, and compares every application table's complete row
digest/count plus table/sequence ownership and ACLs while application writers
are stopped. This tests one cluster with existing global roles, not disaster
recovery onto an empty cluster. Dumps remain in the disposable DB container.
Database ACLs are applied explicitly to the differently named restore target;
schema and column grants are checked as well. ACL comparison expands PostgreSQL
defaults, so equivalent implicit and explicit owner grants compare equally.
For a repeat after six completed outage/session checks, `s7_backup.py` reruns
only the backup gate; it still refuses an existing restore target.

Container execution exposed and corrected Windows CRLF in the gateway startup
script, non-root Nginx temporary-directory defaults, Vite cache ownership and
frontend DNS host admission. Docker init forwards termination signals to Python
and Node. These were observed startup failures, not merely Compose lint findings.

## Production limitations

This is a synthetic local acceptance stack, not a production deployment:
development WSGI/preview servers, DEBUG and HTTP at the browser edge, test-only
high login/import budgets, 30-day generated certificates, no automatic secret
rotation, bounded-worker capacity assessment, scheduled outbox delivery,
monitoring, approved RPO/RTO, external encrypted backups or empty-cluster role
restoration. PostgreSQL unavailability can produce a generic HTTP 500; no
successful write is accepted. Production needs TLS/secure cookies/DEBUG off and
reviewed error redaction. Gateway DNS is resolved on startup; container
recreation with changed addresses requires a gateway restart. Runtime restart
with retained addresses is tested separately. No production availability or
visual fidelity certification follows from these tests.

After S7 acceptance, retain the four-service boundary and move to the
[functional gap analysis](../functional-gap-analysis.md); no additional service
extraction is planned.
