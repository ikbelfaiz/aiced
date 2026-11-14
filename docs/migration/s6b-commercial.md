# S6b: independent Commercial extraction

**Status: S6b implemented and verified in the local synthetic deployment.**
IAM, Client & CRM, Commercial and Data Integration are actually running as four
separate Django processes with enforced data boundaries. The active writer is
Commercial after an actual post-write rollback and forward cycle. Production
readiness and container execution are not claimed.

## Architecture and actual interfaces

The remaining backend is Client & CRM (`iam_consumer.settings`), not an IAM or
Commercial SQL consumer. IAM and Integration keep their S5 owned schemas and
processes. Commercial uses its own Django entry point, `commercial_service`, with
only `commercial_store` models registered. There is no auth.User, session, Client
or Integration ORM registration in Commercial. Shared Python HTTP/validation
utilities do not grant access to another service's data.

| Service | Local process | Persistent domain | Public route patterns |
|---|---|---|---|
| IAM | `iam_service.settings`, port 8001 | `aiced_iam` | Existing 10 |
| Client & CRM | `iam_consumer.settings`, port 8000 | Existing public Client tables and local refs/journal | Existing 17, including health, composed schema and federated audit |
| Commercial | `commercial_service.settings`, port 8004 | `aiced_commercial` | Existing 2 opportunity patterns |
| Integration | `integration_service.settings`, port 8002 | `aiced_integration` | Existing 9 |

Nginx remains the sole frontend API entry, port 5173 in this local deployment.
React, URLs, cookies and individual API calls do not change. All 38 patterns / 47
method-path pairs and the entire composed OpenAPI object must match the frozen
baseline, not just a count. Inactive Commercial routing defaults to the existing
backend so earlier M1/M2 configurations still render correctly.

Transferred public routes:

- `GET, POST /api/clients/{party_id}/opportunities/`
- `GET, PATCH /api/clients/{party_id}/opportunities/{activity_id}/`

Internal interfaces:

- IAM signed principal/grant snapshot and audit receipt contracts from S2/S5.
- Client `POST /internal/v1/clients/authorize`: actor, party, organization and
  Client version; Client intersects clients.view, opportunities.view/manage and
  prospects.view on that same object. It is now a stateless authorization reader.
- Commercial `POST /internal/v1/commercial/audit/query`: scoped, bounded keyset
  pages, authenticated Client producer plus a freshly verified human audit scope.
- Commercial `/health/ready`: owned-schema/admission health; protected operations
  still fail closed when IAM or Client is unavailable. Local health alone does
  not certify peer availability or shared-database topology.

## Ownership, references and migration lineage

`aiced_commercial.clients_opportunity` becomes canonical. Its original UUIDs,
Decimals, nullable fields, dates, timestamps, authors and versions are copied
without ORM auto_now changes. Commercial has its own `django_migrations` and
initial/fence migrations. All old migration files and recorders remain intact.

New owned tables: `clients_opportunity`, `commercial_store_partyref`,
`commercial_store_actorref`, `commercial_store_journal`,
`commercial_store_outbox`, `commercial_store_internalnonce`,
`commercial_store_runtimestate`, and `django_migrations`.

Opportunity's two FKs now target local PartyRef/ActorRef records, not Client or IAM
models. PartyRef contains only verified internal party/org UUIDs and is immutable;
author references come from IAM's authenticated actor. These are not replicated
identities or permission caches. Object access is verified live through Client.
Client runtime SQL guards reject party hard deletion, rekeying or reparenting;
there is no public hard-delete endpoint. Future retention/tombstone workflows
require a separate reviewed contract. Unreviewed organization remapping fails.

`public.clients_opportunity` remains an inaccessible historical/cutback copy,
owned by a NOLOGIN archive role while Commercial is active. Neither the Client
runtime nor its old table owner can use that archive as an alternate writer.
Its historical FKs are deliberately retained. Existing Client Django metadata is
also retained for old migration history and the composed public schema, not used
as an active Commercial ORM access path. Middleware rejects direct retired
opportunity routes and SQL privileges enforce the boundary independently.

Client adds a CommercialJournalRef registry for transferred audit identities and
an additive scope/reference-guard migration. Its existing Client/CRM/prospect/
interaction tables stay in place. No Client business table or IAM/Integration
ownership is transferred in this increment. Public schema contains historical
archives as well as active Client tables; it is not all owned by Client.

## Concrete concurrency protocol

The protocol deliberately requires the **same PostgreSQL database/instance** for
all four services, with separate roles/schemas. It uses transaction-level advisory
locks, not an HTTP check followed by an unprotected write:

1. Commercial enters its owned cutover gate, then holds the shared IAM revocation
   barrier and shared Client scope fence through its local commit.
2. It revalidates IAM after waiting for admission, then requests fresh Client
   object authorization. It locks its own opportunity for updates, checks the
   optimistic version, and commits data + required journal + outbox together.
3. Client mutations take exclusive Client scope admission after local org
   serialization and the IAM shared barrier, before object row locks/writes.
   Statement triggers on Party and Prospect cover direct DML and truncation too.
   IAM security mutations retain the exclusive IAM barrier from S2.
4. Authorization readers do not reacquire conflicting admission locks or update
   Client actor/org reference rows. Otherwise a queued Client writer holding an
   org row could deadlock a Commercial authorization RPC; the real-process probe
   explicitly reproduces this situation and requires the reader to finish.

An admitted write finishes before conflicting reassignment/revocation commits.
A queued write rechecks after the winning change and is denied if scope or user
access was removed. Client prospect classification is included in that fence.
The Client fence is conservative and global, rather than a premature per-party
coordination design. High write contention and separate database instances are
not supported without another tested protocol.

Client grant snapshots are request-local, attached to a newly authenticated
actor; no grant cache is stored in PostgreSQL or shared across requests. Write
admission always replaces that snapshot after acquiring the barriers. This avoids
many repeated IAM RPCs in one Client response while preserving write revocation
checks. All services use request-scoped DB connections; idle persistent sockets
exhausted the portable database during the first browser workload. Production
still requires bounded WSGI concurrency and capacity verification.

## Signing and trust

| Pair | Verified producer | Audience |
|---|---|---|
| Commercial to IAM | commercial | iam / audit, IAM-only receiver |
| Commercial to Client | commercial | client only |
| Client to Commercial audit reader | client_crm | commercial only |

Each pair has a distinct random secret/key ID, separate from Django and Gateway
keys. Client does not hold Commercial's IAM signing identity. Commercial does not
hold Client's IAM identity. Receiver configuration binds producer/audience; user
or role headers cannot choose identity. S2's path/body/method/timestamp signature,
committed nonce uniqueness, 30-second signature window and bounded HTTP deadlines
remain in use. There are no redirects, mutation retries or stale-auth fallbacks.
Secrets/roles/backups stay in ignored private local files. Remote HTTP is refused;
container peers require TLS and supplied CA/server certificates.

## Audit, retries and business transactions

Commercial business change, immutable Journal and Outbox commit in one local
transaction. Real injected Journal and Outbox failures must undo the opportunity
and version change. The existing event name `clients.opportunities_saved` and
minimal S2 receipt envelope remain compatible. Context/notes are omitted from
central delivery. Shared audit-envelope code has no business ORM imports.

`deliver_commercial_audit --limit 1..100` sends pending events using the scoped
machine identity outside business transactions. Failed delivery leaves a durable
pending event and attempt count. IAM receipt deduplication makes a lost-ack replay
safe. A restored probe requeues an accepted event and verifies no second receipt.
Automatic scheduling/monitoring of these workers is not supplied by this change.

Public audit immediately merges IAM, Client, Integration and Commercial journals,
scoped before counting/pagination. Copied-back event IDs are excluded from Client
when Commercial is active, avoiding duplicate history. A peer failure never
returns a successful partial audit page. Raw source cells and financial account
values are not copied into audit delivery.

Public creation retains the pre-existing POST semantics; the Gateway does not
retry it automatically. Duplicate/stale PATCH is rejected by version checking and
internal signed-request replay is rejected. No new public exactly-once POST or
idempotency-key contract is claimed. Import idempotency remains unchanged.

## Safe transfer, cutover and rollback

The tools refuse production/remote DBs and unmarked restore targets. Initial
local cutover also refuses an existing Commercial schema or an incomplete prior
transition. A current-source-hash restored rehearsal must pass first.

- Full exported-snapshot backup is restored before any ownership DDL. Validation
  compares table values/counts, schema, FKs/checks, indexes/triggers/functions,
  sequence high-water state, owners and table/schema/function/default/database
  privileges. Global roles must already exist on the restore cluster.
- Stop the supervised application and confirm listeners close, including the
  Commercial port on later transitions. Take and restore another stopped backup.
- Apply additive Client preparation and owned Commercial migrations, validate
  refs, copy exact data/history. No migration deletion, reset or production copy.
- Copy, FK validation, ACL fencing and activation share an offline transaction.
  The public opportunity table is locked exclusively across that transaction.
  `SET CONSTRAINTS ALL IMMEDIATE` drains deferred FK checks before ownership DDL;
  constraints are validated, never disabled. Commercial remains frozen on failure.
- Change compatible Gateway routing and private runtime configurations, start the
  independently supervised processes, then verify real HTTP/data/role isolation.

After new writes, rollback is a coordinated maintenance operation: stop writers,
verify new backups, freeze Commercial, copy canonical new opportunities, actors,
immutable journals/outbox delivery states back, validate exact parity, restore
legacy ownership/ACLs, activate one writer, route and restart. Never restore an old
dump over newer commits or just change Nginx. Immutable event collisions and
missing/changed Client references abort for review. Deleted canonical records
are not silently resurrected/removed. Forward again carries new legacy writes.
S6 must be rolled back before S5 IAM ownership changes; the old tool refuses the
wrong order. No distributed application transaction or broker is introduced.

## Local startup and operations

Use these only with the generated private portable-local configuration:

```powershell
$deployment = '.local/s4-active/b1cb997fda7f49a4a6331979c656bfb6'
# Full local supervisor; do not start duplicate manual listeners.
python scripts/run_s4_deployment.py --directory $deployment

# Alternative independently started Commercial process.
python scripts/run_commercial.py --env-file "$deployment/commercial-env.json" runserver 127.0.0.1:8004 --noreload
# Offline owned migrator only.
python scripts/run_commercial.py --env-file "$deployment/commercial-migration-env.json" migrate --noinput
# Bounded signed outbox delivery, safe to retry.
python scripts/run_commercial.py --env-file "$deployment/commercial-env.json" deliver_commercial_audit --limit 50

# Repeatable full restored rehearsal; never transfers active ownership.
python scripts/s6_rehearsal.py --confirm-local-rehearsal
# Initial local cutover: supply the actual passed report for the current source.
python scripts/s6_local.py --directory $deployment --confirm-local-cutover --verification-report <passed-report.json>
python scripts/s6_verify_local.py --directory $deployment --phase initial
# Post-write rollback and forward, with fresh verified backups each time.
python scripts/s6_local.py --directory $deployment --confirm-local-cutover --rollback
python scripts/s6_verify_local.py --directory $deployment --phase rollback
python scripts/s6_local.py --directory $deployment --confirm-local-cutover --forward
python scripts/s6_verify_local.py --directory $deployment --phase final
```

Verification phases create clearly synthetic opportunities and keep their private
UUID/session/configuration evidence under the deployment directory. They are
local acceptance helpers, not production migration or health-check commands.

Container definition: `docker compose -f compose.yaml -f compose.s6.yaml ...`.
S6 includes the S5 IAM/Integration services; do not stack S4/S5 overlays. Supply
private runtime/migrator env files and CA, IAM, Client, Integration and Commercial
certificates under the documented local TLS mount. Commercial uses public 8004 /
private TLS 8445, Client public 8000 / private TLS 8446. Only public API routing goes
through Nginx. Runtime credentials never receive migrator ownership roles.

## Verification results and evidence

[Current sanitized ownership/process inventory](s6b-inventory.json).

| Verification | Result |
|---|---|
| Existing backend + real-Nginx suites | **139 passed**, final native exit 0; `.local/s6b-final-regression.log` |
| IAM service | **5 passed**, actual restricted configuration |
| Integration service | **8 passed**, targeted `integration_store`; an empty `integration_service` discovery is not counted |
| Isolated Commercial service | **5 passed**: owned app/migration graph, strict estimates/fields, trust scope and transport policy |
| Full restored HTTP/PG gate | Passed against current source hashes; four distinct Django processes plus actual Nginx |
| Browser | **11 development + 6 compiled passed**, unchanged assertions, 60-second whole-workflow budget |
| Build/contracts | TypeScript and production build passed; entire public OpenAPI equals frozen baseline; 38 routes / 47 method-path pairs |
| SQL isolation | Actual LOGIN credentials deny Commercial reads/writes to Client/IAM/Integration tables and Client access to owned/archived opportunities; runtime flags and all owned FKs inspected |
| Concurrency | Queued and admitted reassignment races, held-org-row reader deadlock regression, user/role/session revocation and prospect classification passed |
| Audit/duplicates | Journal and Outbox failure undo data/version; duplicate/stale PATCH 409; forged/audience/replayed packets denied; lost audit acknowledgment replay creates no extra receipt |
| Outages/restarts | Client/IAM failure closes access without new writes; independent Client/Commercial/IAM restarts retain sessions in restored processes |
| Actual local cutover | Initial service write, rollback retaining version/Decimal/history, new legacy write and forward again all verified through Gateway |
| Live Commercial restart | Own PID replaced; Client/IAM/Integration/frontend PIDs unchanged; same session still retrieves its opportunity |
| Existing records | **12 Client/Integration business tables unchanged; all 17 pre-existing opportunities match exactly** |
| Backups | Fresh live/stopped backups restored for initial, rollback and forward. Final **80-table** backup restored; independent restored IAM/Client/Commercial processes retrieve both new records |
| Rollback ordering | S5 IAM rollback refuses while S6 Commercial is active, before any ownership mutation |
| Docker | Final Compose configuration validates; installed Docker CLI cannot reach Docker Engine. No container build/start or production security claim |

Passed restored gate:
`.local/s6b-rehearsal/9c45a9c496cb4434b58361993a0a752f/report.json`.
Actual private evidence under
`.local/s4-active/b1cb997fda7f49a4a6331979c656bfb6/`:
`s6-state.json`, `s6-active-verification.json`, `s6-restart-verification.json`,
`s6-preservation-verification.json`, `s6-final-restored-process-verification.json`,
and six live/stopped restore-verification reports. Dumps/configuration/credentials
remain ignored. Earlier failed rehearsal reports remain preserved.

Current process IDs at inventory capture: Client **14816**, IAM **33560**,
Integration **32072**, Commercial **18392**. These are observed local PIDs, not
fixed startup requirements; consult `process-status.json` after a restart.

Observed rehearsal corrections retained in private reports:

- Initial backup helper accidentally used the restricted runtime for CREATE DB;
  disposable DB administration now uses only the offline administrator.
- A positive test used a manager without commercial grants; it now uses the
  explicitly authorized synthetic operator. Audit uses the separate audit reader.
- One inherited Integration audit URL reached the active local listener and was
  denied; no business/ownership transfer occurred. All rehearsal peer URLs were
  corrected. Its security trace is retained, not erased; subsequent full active
  snapshot comparisons must pass.
- Persistent connections exhausted ordinary slots; request-scoped connections
  and request-local grant consolidation fixed the workload without raising limits.
- Compiled tests reused the already published development workbook; separate
  synthetic workbooks restore test isolation without weakening publication rules.
- Ownership DDL after copied rows initially hit pending deferred FK events;
  explicit immediate validation allows safe atomic copy/fence/activation.

## Remaining deployment risks

Docker Compose parsing/configuration alone is not container execution. Docker
Engine availability and actual container results are stated in the final results.
No production readiness, load/HA or hardened TLS/WSGI security claim is made.
Shared-PG lock topology must be verified for any other deployment; cloning service
DBs onto separate instances breaks the coordination guarantee. Bounded worker/
connection capacity, approved backup retention/global-role/HBA recovery, secret/
certificate rotation, monitoring, nonce retention and worker scheduling remain
operational prerequisites. Client historical compatibility models/archives remain
retained and are protected by ACLs rather than deleted for cosmetic separation.

Carthago is strictly read-only. No real connector, authoritative identity/account
merge, field mapping, source-data overwrite, new KPI, campaign or appointment
feature is introduced. Prospects, interactions and editable Client profiles stay
Client-owned. Analytics/Reporting and AI are not extracted by this increment.

## Changed files and next work

[Complete changed-file inventory](s6b-files.json) lists source/document paths.
Major changes are the independent `commercial_service` / `commercial_store`,
neutral signed-contract utilities, Client scope/reference guards, scoped trust,
request-local grants/connection lifecycle, fourth audit stream, Gateway/supervisor,
owned Docker/Compose definition and guarded backup/transfer/verification tooling.
No React business source, historical migration, private reference or upload was
changed/committed. Client, IAM and Integration ownership is retained.

The four-service target is complete **locally**. Next architectural work is
containerized deployment and production security/operational verification, not
more microservices. Functional roadmap remains appointments/campaigns and approved
commercial/reporting rules as requested, with Analytics and Audit bounded modules.
Carthago access/mapping approval still gates authoritative integration operations
only; it does not block ordinary AICED CRM/opportunity/import development.
