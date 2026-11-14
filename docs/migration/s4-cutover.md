# S4 — Controlled Integration cutover

**Later state:** [S5 IAM extraction](s5-iam.md) is active locally. Roll back S5 before any S4 rollback; the S4 tool refuses the unsafe order. This S4 report remains historical evidence.

## Verified status — 14 November 2026

**S4 is active and verified in the portable local development environment.**
Normal `http://127.0.0.1:5173/api/imports/...` requests now reach the separate
Integration process on port 8002. The existing backend/IAM/Client/Commercial
residue remains on 8000; the signed IAM facade is private on 8001. The React
source, 38 public route patterns and 47 method/path contracts are unchanged.
No production deployment was accessed. Docker is unavailable here.

Local state directory (private, ignored):
`.local/s4-active/b1cb997fda7f49a4a6331979c656bfb6/`.
`routing-status.json` reports `mode: service`, upstream `8002`; both private
control rows record the canonical owner `service`. Only Integration admits that
mode; the legacy adapter admits only `legacy`. `frozen` admits neither.

See the sanitized [schema/route inventory](s4-inventory.json). The old S2
`service-inventory.json` remains a dated historical inventory.

## Initial audit and chosen sequence

The attached S4 request is the execution scope. The actual S3 candidate has a
separate DRF entry point, local references/journal/outbox, two owned migrations,
signed IAM HTTP authorization and a restricted schema role. S3 evidence exists
under the private run `845cee4b452d4f81b6127e1d44ebe0b8`; it did not cut over the
normal application. Docker is not installed on this workstation.

Nine public import route patterns (ten HTTP operations, because policies accepts
GET and POST) can move together without a frontend URL change:

- GET `/api/imports/context/`
- GET `/api/imports/{organization}/batches/`
- POST `/api/imports/{organization}/upload/`
- GET `/api/imports/{organization}/batches/{batch}/`
- GET `/api/imports/{organization}/batches/{batch}/rejections/`
- POST `/api/imports/{organization}/batches/{batch}/publish/`
- GET/POST `/api/imports/{organization}/policies/`
- POST `/api/imports/{organization}/policies/{policy}/approve/`
- POST `/api/imports/{organization}/policies/{policy}/revoke/`

Validation/staging happen during upload; there is no separate mapping editor.
The approved rule selects a candidate key column and date interpretation.
Publication writes immutable SourceSnapshot rows and publication metadata only.
It does not call Client/CRM, create/update identities/accounts, or synchronize
Carthago. Adding such a call would violate the unapproved-mapping restriction.
End-to-end acceptance must therefore prove client/account data is unchanged.

Gaps before active routing: immediate scoped public audit visibility; fencing
old endpoints/jobs/SQL writes; reverse transfer after new service commits;
health/readiness and deployable active configuration. No production cutover is
authorized or claimed.

Sequence:

1. Re-run the baseline; preserve historical migrations and public contracts.
2. Add service-owned replay protection/private audit reads and authorized audit
   federation; fail closed rather than return a partial public audit listing.
3. Add local import admission/freeze controls and database writer fences.
4. Rehearse backup/restore, forward parity, active Gateway routing, complete UI
   publication, post-commit reverse transfer, stale/in-flight rejection and retry.
5. Only after rehearsal passes, back up the intended local environment, freeze
   imports, copy/verify, fence the previous writer and enable the service routes.
6. Report the actual routing state and results; keep unrelated services intact.

The sequence above was implemented and exercised as detailed below.

## Architecture, ownership and contracts

The existing parser, templates, serializers and publication business rules are
reused through `ingestion.runtime` ports. There is no second Excel importer.
Integration owns 11 tables in `aiced_integration`: four import-domain tables,
ActorRef/OrganizationRef, Journal/Outbox, InternalNonce, RuntimeState and its
own Django migration recorder. It registers no IAM/session/Client models.

The four `public.ingestion_*` domain tables are retained as protected archives
and rollback targets, not as an active second writer. Their owner is a NOLOGIN
archive role. The old runtime's DML rights are revoked; database writer triggers
also check admission. Read access is retained for controlled historical
inspection; normal old import HTTP routes return 503, and the updated legacy
service adapter also refuses background calls while inactive. Stop any obsolete
jobs during deployment; no import queue/worker existed to extract here.

The active runtime has SELECT/INSERT on its own domain/reference/journal tables;
UPDATE is limited to policy approval/revocation, batch publication metadata and
outbox delivery columns. It cannot update staged cells or snapshots, delete
audit/history, run DDL, SET ROLE to its owner, create temporary tables or use the
public schema. Nonce maintenance can delete expired technical replay digests.
Its owner is NOLOGIN, its migrator is a separate NOINHERIT login, and runtime has
no role memberships or superuser/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS flags.
Every active Integration FK stays inside its schema. Historical IAM FKs in the
archived public tables were preserved.

Two additive legacy migrations (`ingestion.0006`/`0007`) add its deployment
control and writer fence. Two new owned migrations (`integration_store.0003`/
`0004`) add service replay protection/control and the owned writer fence; S3's
first two migrations remain intact. No historical migration was deleted or
reset, and no table was dropped. There are now 34 public tables and 11 owned
Integration tables. IAM/Client/Commercial ownership was not extracted.

Internal HTTP interfaces added during S4:

| Listener | Contract | Authorization |
|---|---|---|
| IAM facade | POST `/internal/v1/imports/audit-scope` | Signed Integration identity plus fresh delegated user session; returns full-organization `audit.view` scope only. |
| IAM facade | POST `/internal/v1/integration/ready` | Signed Integration machine probe; verifies IAM DB access and returns coordination DB name. |
| Integration | POST `/internal/v1/integration/audit/query` | Signed IAM peer, service-owned nonce/replay store, and fresh delegated audit grants checked through IAM. Applies org filtering before count/pagination. |
| Integration | GET `/health/live`, `/health/ready` | Minimal private-network probes; readiness checks owned DB privileges/state and signed IAM connectivity. No business data. |

The private audit API uses bounded chunks and a strict descending timestamp/UUID
cursor for subsequent chunks. New events cannot shift an offset and duplicate
the previous chunk. The public audit API retains its existing numbered-page
shape, ordering, fields and permission requirement. IAM's own scoped journal
excludes copied import events, then merges the authoritative Integration journal
with the same ordering and no duplicates. A second organization check defends
against malformed upstream results. No SQL reads of Integration tables are
granted to the backend. Failure, invalid data or transfer maintenance returns
503 rather than a partial audit page. Receipts remain deduplicated delivery
metadata, not a substitute for immediate journal visibility.

## Authentication, revocation and local transactions

S2 HMAC signatures still bind service key ID, audience, timestamp, random nonce,
method, path and exact body digest. New private Integration requests use its own
replay table, not IAM SQL. The service accepts only its outbound identity and
the IAM inbound Integration-audience key. Arbitrary browser user/role headers
remain irrelevant. The Gateway key authenticates metadata only, never users.

Original session cookie/CSRF behavior is delegated to IAM from actual request
credentials. IAM retains its existing Django secret and sessions; Integration
has a different Django secret and no IAM database credential. Upload/preview/
history/CSV/policy/publication still require the existing intersection of
full-org import and financial permissions plus the operation capability.
Audit consultation preserves the separate `audit.view` rule.

Import mutations hold their local admission gate, organization quota/idempotency
lock, and S2 shared revocation barrier, then obtain fresh IAM authorization.
IAM permission changes/deactivation/logout participate in S2's exclusive barrier.
A freeze takes the exclusive deployment gates, drains admitted writes, and
changes both local control rows in one deployment transaction. Waiting writes
recheck state; they cannot commit after freeze using a stale admission.

Business records, required local journal and outbox commit together. Audit
insertion failure rolls back business state. Delivery happens outside the
business transaction, with bounded attempts, stable event IDs, new signed
nonces, receiver deduplication and retained pending failures. Central outage
does not erase local audit. No distributed business transaction was introduced.

## Reproduction and startup

The complete isolated rehearsal is:

```sh
python scripts/s4_rehearsal.py --confirm-local-rehearsal
```

It first verifies a restored backup, then migrates/copies into a marked restored
database, runs real processes/Nginx/Chromium, tests active routing and reverse
transfer, and removes its own scratch databases/roles. It does not modify the
application database. Avoid concurrent manual activity when a full preservation
gate is comparing that database before/after.

Local cutover provisioning requires an S4 report with passing rollback/Client
preservation gates and matching recorded code hashes:

```sh
python scripts/s4_local.py --confirm-local-cutover --verification-report <private-S4-report.json>
```

This command supports ONLY DEBUG development, loopback PostgreSQL port 55432,
database `aiced`. It refuses an existing owned schema rather than replacing
one. It verifies backups on disposable restores before ownership changes and
again while imports are frozen. Exported repeatable-read snapshots keep dump
and fingerprint coherent if unrelated users write during backup. Restore checks
cover records, owned schema metadata/sequences, owners and effective table,
column, schema and function privileges. Explicit-default versus NULL ACL text
is compared by actual grants/grantors/grantees/options, not ignored wholesale.

Start the prepared local deployment in a terminal:

```sh
python scripts/run_s4_deployment.py --directory .local/s4-active/b1cb997fda7f49a4a6331979c656bfb6
```

It runs four existing application processes (public backend, private IAM facade,
Integration, Vite) and Nginx. Failed processes restart independently; an
Integration failure does not shut down the other processes. This supervisor is
for local development, not a production process manager. The supervisor running
during verification was launched hidden. Use its stop command instead of
launching a second instance on the same ports:

```sh
python scripts/run_s4_deployment.py --directory .local/s4-active/b1cb997fda7f49a4a6331979c656bfb6 --stop
```

To run Integration alone, with the private IAM facade already running:

```sh
python scripts/run_integration.py --env-file .local/s4-active/b1cb997fda7f49a4a6331979c656bfb6/integration-env.json runserver 127.0.0.1:8002 --noreload
python scripts/run_integration.py --env-file .local/s4-active/b1cb997fda7f49a4a6331979c656bfb6/migration-env.json migrate --noinput
```

Never give the migration environment to the runtime server. The second command
is an explicit offline deployment step, not application startup.

Delivery and replay maintenance:

```sh
python scripts/run_integration.py --env-file .local/s4-active/b1cb997fda7f49a4a6331979c656bfb6/integration-env.json deliver_integration_audit --limit 1000
python scripts/run_integration.py --env-file .local/s4-active/b1cb997fda7f49a4a6331979c656bfb6/integration-env.json prune_integration_nonces
```

Schedule bounded outbox retries and nonce pruning operationally; no automatic
queue was added. Monitor readiness, Gateway 502/503/504, local process logs,
pending outbox count/oldest event/attempts and explicit delivery command failures.
Never log request cookies, signing keys, raw Excel cells or private env files.

## Compose configuration (not executed on this workstation)

`compose.s4.yaml` overlays the existing Compose setup with independent
Integration and private IAM-facade processes, owned migration job, readiness
check, verified TLS between containers and explicit import routing:

```sh
docker compose -f compose.yaml -f compose.s4.yaml up -d
```

Run this only after the appropriate database backup/migration/copy/fence procedure
has been rehearsed and approved in that environment. The local-only provisioning
tool is deliberately not an unattended production migration tool. The base
Compose file alone remains suitable for a fresh legacy development database; it
does not switch an active S4 database back by itself.

Provide private `.env.iam-internal`, `.env.integration`,
`.env.integration-migrator` and `.local/s4-tls/` files outside version control:

- Backend/IAM: IAM database credentials, original Django secret, Gateway key,
  key registry, `AICED_INTEGRATION_AUDIT_KEY_ID`.
- Integration: its restricted credentials/schema, unique Django secret, Gateway
  metadata key, `AICED_INTEGRATION_KEY_ID`, and its own/authorized inbound IAM
  key registry. No IAM DB password/session secret.
- Migrator: separate login/password and `AICED_MIGRATION_ROLE`; never runtime.
- TLS: trusted CA, IAM certificate/key (SAN `iam-contracts`), Integration
  certificate/key (SAN `integration`). Local mounted files must be readable by
  the image's unprivileged application user.

Compose connects Integration to `https://iam-contracts:8443`; the backend audit
reader connects to `https://integration:8444`, using `SSL_CERT_FILE`. Integration
also listens internally on HTTP 8002 for the existing Gateway. No new host
application port is published. In the active overlay, `INTEGRATION_UPSTREAM`
defaults to `integration:8002`; explicit `backend:8000` is a routing rollback
setting only AFTER data transfer and admission changes. `/internal/` and private
health paths are not added to the Gateway API locations.

YAML syntax was parsed; Docker build/run, container networking, certificates and
production TLS were NOT verified. Development WSGI/Vite servers remain unsuitable
as a production hardening sign-off. If a recreated container changes its IP,
reload/recreate this statically resolved Nginx deployment. No mesh/resolver
infrastructure was introduced to claim untested HA.

## Rollback and recovery — tested before and after commits

1. Stop old/obsolete domain jobs and automatic delivery workers in the deployment
   environment. Freeze both admissions with exclusive gates; let already admitted
   writes finish. New/queued imports receive 503 and can retry after maintenance.
2. Back up the latest state and verify restore. Do not restore the pre-S4 dump
   over later committed work.
3. Reverse transfer Policy → Batch → StagingRow → Snapshot, preserving UUIDs,
   immutable columns, source dates/digests, review/publish status and all audit
   and outbox identity/delivery metadata. Validate original IAM FKs again through
   SQL constraints. Do not delete rows missing from the source.
4. Existing immutable-ID conflicts abort the whole transfer. Mutable approval/
   publication fields follow the canonical source. Delivery attempts/acknowledgments
   are retained monotonically; no journal or outbox is erased.
5. Verify parity, restore the old domain writer's ownership/DML, set canonical
   owner `legacy` in both private controls, THEN reroute Nginx. The service now
   refuses business operations. Keep its schema/journal for recovery.
6. Verify historical and new published batches, and continue a previously staged
   batch. Partial failures stay frozen for investigation/forward repair; do not
   bypass a failed guard or simply edit the routing file.

For this prepared local deployment:

```sh
python scripts/s4_local.py --confirm-local-cutover --rollback .local/s4-active/b1cb997fda7f49a4a6331979c656bfb6
```

The running supervisor notices the explicit deployment routing file only after
transfer/activation. Nginx is gracefully replaced while application processes
remain running. Stale upstream connections can receive 503 during that window;
the database fences prevent them from committing to the wrong owner. Import
requests must be retried with the same file bytes/metadata or publication ID.

The tested forward return after rollback is:

```sh
python scripts/s4_local.py --confirm-local-cutover --forward .local/s4-active/b1cb997fda7f49a4a6331979c656bfb6
```

It repeats freeze/backup/restore/parity/copy/ACL/activation before routing back to
Integration. New publications made during the legacy interval are preserved.
Never unapply audit/immutability migrations to simplify a rollback.

## Executed verification and evidence

| Check | Result |
|---|---|
| Full main-backend regression | 122 tests passed in the full safety gate; final full rerun also passed 122 tests in 82.329 seconds (`.local/s4-final-backend.log`). |
| Gateway compatibility | 10 real-Nginx tests passed; 38 public route patterns retained. |
| Existing React regression | 11 development and 6 compiled-bundle Chromium tests passed. |
| Owned service tests | 8 passed: isolated models/migration graph/routes, no foreign ORM, delegation/scope checks and bounded HTTP response deadline. |
| S4 React flow | Login, restored history, real upload/duplicate preview, two-actor rule approval and partial immutable publication, IT denial passed through Nginx/Integration. |
| S4 security/data | Real restricted LOGINs; forged headers/replayed signatures; cross-org and financial denial; revocation overtaking a queued write; frozen-writer race; required audit/outbox failure rolling back business data; offline IAM/Integration failures; outbox retry passed. |
| Rollback | Offline immutable-conflict probe rejected; repeated reverse transfer idempotent; new staged service batch continued and published through the legacy Gateway; forward re-cutover retained that publication. |
| Actual local deployment | Normal port-5173 upload/staging/publication/replay/audit, own-schema SQL, old-writer DML rejection and Client/CRM/account fingerprints verified. Actual rollback and forward switch also verified. |
| Independent restart | Integration PID changed while backend/IAM/frontend PIDs stayed unchanged; main API returned 200 during restart; published state remained intact. |
| Audit delivery | Actual owned worker delivered 11 pending events with 0 failures. |
| Backup/restore | Pre-cutover, frozen, rollback, forward and final snapshots restored on disposable databases; full records, schema metadata/sequences and effective table/column/schema/function privileges checked. |
| Safety tooling | 14 unit tests passed; three Compose files parsed as YAML. |

Private evidence:

- Final full safety gate: `.local/migration-baseline/419e053ac2c3443889cf2d5563896d0a/report.json`.
- S4 isolated rehearsal: `.local/s4-rehearsal/9f68c275c8f5419890017081682247b5/report.json`.
- Final backend log: `.local/s4-final-backend.log`; targeted updated audit/import tests also passed (20 tests).
- Actual local data/routing/HTTP checks: the active directory's `state.json`,
  `routing-status.json`, `http-verification.json`, `process-status.json` and
  `final-backup-verification.json`. Secrets/dumps are not committed or included
  in public documentation.

Failures were not suppressed: the first full gate detected activity in the live
demo during fingerprint comparison; its disposable suites passed but the gate
failed closed. The quiescent rerun passed. The first actual forward rollback
preflight rejected an explicit-default ACL/NULL serialization difference; imports
remained frozen. Effective grant comparison was implemented and the same forward
switch then passed, with a subsequent full metadata/privilege restore check.

## Limits and next stage

S4 completion is local, not a production deployment claim. Production backup
approval, retention/RPO/RTO, TLS/container execution, hardened WSGI/process
supervision, capacity/load, prolonged partitions/failover and monitoring remain
required. The legacy IAM/residue database role is not newly hardened as a fully
extracted service; the isolated Integration role is enforced. Cluster-wide HBA/
cross-database CONNECT policy is still an operational prerequisite.

Audit federation keeps bounded memory and a 12-second request budget. Very deep
pages/large contexts can return 503 instead of partial results; benchmark before
production. Numbered public pages are live reads, not an immutable multi-request
snapshot. Cursor chunks prevent insertion-induced duplicate rows within a read.
The S2 revocation barrier is database-scoped/global: IAM and Integration must use
the same PostgreSQL database on the same instance. Readiness checks DB name and
transport, but do not replace topology verification or HA testing.

No real Carthago connector, field mapping, identity/account merge, financial KPI,
appointments, campaigns, reporting or AI was added. Read-only adapters remain
replaceable, and unresolved identities stay unmerged in versioned source history.

Next recommended migration stage is the planned IAM extraction prerequisite
review (S5), including remaining ORM consumers, sessions, private contracts and
least-privilege deployment. **Do not begin it as part of S4.**

## Changed source files

- `backend/core/{import_gate,import_gate_middleware,cutover_sql}.py`: admission,
  freeze and DB fence infrastructure.
- `backend/ingestion/{models,runtime}.py`, migrations `0006`/`0007`: retained
  legacy controls and refusal of inactive callers.
- `backend/integration_store/{models,tests}.py`, migrations `0003`/`0004`, nonce
  maintenance command: owned controls/replay protection, isolated tests.
- `backend/integration_service/{access,journal,settings,urls,private,serve}.py`:
  scoped authorization/admission, audit query, readiness and container listeners.
- `backend/internal_api/{client,security,views,urls,serve}.py`: common request
  credential extraction, configurable owned nonce model, IAM scope/readiness.
- `backend/audit/{views,federation,test_federation}.py`: compatible scoped merged
  audit reads and regressions.
- `backend/config/settings.py`, `backend/service_architecture/ownership.py`:
  peer audience/routing configuration and control-table classification.
- `scripts/{s3_database,s3_rehearsal,s3_browser.mjs,migration_baseline,run_gateway}`:
  reused safety/consumer harnesses, snapshot backup support and explicit routing.
- `scripts/{s4_transfer,s4_local,s4_rehearsal,run_s4_deployment}.py` and
  `scripts/tests/test_s4_transfer.py`: freeze/parity/forward/reverse tools,
  local startup and safety tests.
- `compose.s4.yaml`, migration documentation and current-status entry points:
  opt-in active deployment and operations. No React product source changed.
