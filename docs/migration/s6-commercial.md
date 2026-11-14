# S6: Commercial preparation, before service extraction

> Later status: [S6b is now verified locally](s6b-commercial.md). This document preserves the earlier phase and its evidence.


## Status and decision

S6 is divided into **S6a preparation** and **S6b extraction**. This change implements
S6a only. Commercial is a bounded Python module in the existing Client runtime,
**not an independent service**. IAM and Integration remain the independently
running S5 services. No tables, credentials, routes or ownership have moved.
Four-service architecture has not yet been achieved.

This follows the explicit instruction to split the increment if dependencies
make an immediate separation unsafe. A folder or an extra listener with shared
SQL permissions would not satisfy the requested boundary.

## Actual dependency inspection

Read AGENTS.md, the current coarse-services plan, S5 report/inventory, historical
service-boundary/ownership documents, runtime settings, models, migrations,
public URL configuration, private Client authorization, admission and audit code.
Earlier ownership documents assigning prospects/interactions to Commercial are
superseded: both remain Client-owned.

[s6-inventory.json](s6-inventory.json) records a read-only live S5 PostgreSQL
inspection using the restricted business runtime credential, plus registered
Django Client models and all 38 public routes. It contains aggregate counts and
schema metadata, no customer records or secrets. The inspection found 9 Client
app models, 14 business foreign keys (including the composite assignment FK),
and 17 synthetic opportunities. Counts are observations, not migration proofs.

| Current code/table | Target | Dependencies |
|---|---|---|
| `clients_opportunity` / `clients.models.Opportunity` | Commercial | FK to Client Party; FK to Client-local ActorRef; title/notes/Decimal/status/version |
| Party, PhysicalPerson, LegalEntity, CRMProfile | Client & CRM | Local org/member/actor references; same-org assignment constraint |
| Prospect, Interaction | Client & CRM | Local Party and authors; prospect visibility participates in every object query |
| ExternalIdentity, FinancialAccount | Client & CRM | Read-only source projections; no authoritative source writes |
| `public.audit_*` | Existing local business journal | Mixed Client/Commercial history, local actor/org refs, append-only journal/outbox |
| `iam_consumer_*` | Existing Client compatibility references | Fresh signed IAM validation; no IAM password/session/grant cache |

No incoming SQL FK to Opportunity was found. Its two outgoing FKs cannot simply
be dropped: Party existence/org stability and authenticated author provenance
must have explicit replacements. The model currently has no organization column;
backfill must derive it from Party and verify every row before cutover.

Current opportunity reads share `ActivityView`; writes share Client's
`save_activity`, local Organization and Party row locks and required audit record.
Workspace permission flags remain Client object-scoping decisions. The immutable
public OpenAPI schema remains composed from the historical public URL config.

## Preparation implemented

- `commercial/contracts.py` owns the unchanged OpportunityInput serializer;
  it has no Client or IAM model dependency. `clients.workspace` re-exports it so
  existing view/schema imports and component names remain compatible.
- `commercial/services.py` owns the local opportunity write operation with its
  existing lock/revalidation, version check, Decimal validation, server-selected
  author, required audit and outbox in one database transaction.
- `clients.workspace.save_activity` is a compatibility dispatcher. Interactions
  stay local Client logic. Unknown activity categories now fail validation rather
  than silently becoming opportunity writes.
- New boundary regressions cover scoped denial, input injection, audit rollback,
  exact Decimal/version behavior, audit/outbox persistence and invalid dispatch.

This is an explicit **local adapter**, with documented Client ORM dependencies.
It does not pretend the ORM dependency has already been replaced by HTTP.
No new Django application registration or migration is needed for this stage.

## Two public route transfers planned, none transferred yet

| Path | Methods | S6b owner |
|---|---|---|
| `/api/clients/{party_id}/opportunities/` | GET, POST | Commercial |
| `/api/clients/{party_id}/opportunities/{activity_id}/` | GET, PATCH | Commercial |

All 38 patterns and 47 method/path pairs must remain unchanged. Nginx will route
only these two patterns to Commercial after S6b gates pass. Public schemas,
cookies, CSRF delegation, pagination, errors, Decimal strings, ordering, optimistic
versions and author non-injectability must match. Frontend calls/design do not
change. IAM retains 10 routes and Integration 9; residue currently retains 19.
After extraction Commercial owns 2 and Client/platform retains 17.

## Cross-process security prerequisite

`POST /internal/v1/clients/authorize` already authenticates signed Commercial
callers, resolves a real IAM session and intersects clients.view, action scope,
opportunities.view and prospect visibility. It returns actor/party/org/version.
S5 deliberately does not activate Commercial keys in the Client runtime.
`iam_consumer.settings` currently rejects every non-Client service key. S6b must
change that validation deliberately: keep outbound Client identities separate
from a Commercial-to-Client verification identity restricted to audience `client`.
Never install Commercial IAM/audit signing identities in Client just to make a
call pass. Test wrong-service/audience/signature and replay on the actual deployed
configuration, not only permissive unit-test settings.

That read check is necessary but is not sufficient write fencing. Existing
Client writes use row locks plus a **shared** global IAM revocation barrier.
Two separate processes cannot carry a Party SQL row lock across an HTTP response.
A Client assignment/classification mutation could otherwise commit after a
Commercial scope check and before the Commercial write. IAM's global barrier
protects identity/grant revocation; it does not serialize two shared Client and
Commercial admissions against each other.

Before S6b, implement/test a shared per-party advisory admission protocol on this
same PostgreSQL instance: Commercial holds admission through its local commit,
then makes fresh IAM and Client checks; every Client assignment/classification/
visibility-changing writer takes the corresponding exclusive lock, with the candidate order: local organization serialization, shared IAM barrier,
party admission, fresh authorization, local write/audit, commit. Validate this
order against every existing writer before activating it. Inventory SQL triggers,
admin/jobs and future writers, not just HTTP handlers. Authorization readers must
not reacquire a caller-held conflicting lock. Test waiting writer vs reassignment,
prospect restriction and deactivation in separate real processes; bound timeouts
and fail closed. Do not claim this proposed protocol is implemented here.

## S6b schema, credentials and migration plan

1. Extend frozen inventory with all sequences, indexes/checks/triggers, migration
   dependencies, source/target row fingerprints and audit event ownership. Take a
   full backup and verify restore on a marked disposable database **before DDL**.
2. Create `aiced_commercial` with NOLOGIN owner, separate NOINHERIT migrator and
   restricted runtime. Independent Django entry point registers only owned models,
   migrations, refs/nonces, admission state and journal/outbox. No Client/identity
   apps or shared SQL writer credential. Deny foreign schema reads and writes.
3. Client supplies live bounded object authorization via HTTP. Commercial stores
   immutable party/org and actor identifiers plus minimal locally validated refs,
   never a second editable Client profile or a grant cache. Validate party/org and
   actor equality against signed responses. Preserve UUIDs and timestamps exactly.
4. Introduce owned initial migrations and local constraints: nonnegative 18,3
   manual estimate, TND/status checks, version, indexes and reference consistency.
   Preserve every historical migration. Client keeps its existing migration
   lineage and becomes the remaining independently runnable business service.
5. Freeze both writers under explicit cutover gates, copy validated rows and the
   designated immutable Commercial audit/outbox subset with collision checks and
   exact provenance. Do not delete mixed Client history or duplicate audit pages.
   Extend bounded audit federation/receipts to Commercial, fail closed on outage.
6. Route the two opportunity patterns through existing Nginx, activate scoped
   Commercial HMAC keys/audiences/replay storage, fence old Opportunity SQL writes
   and verify Client cannot read/write the owned schema. No mutation retries at
   the Gateway and no SQL joins across service boundaries.
7. Prove cutover, rollback with new Commercial writes, new legacy writes and
   forward again on restored databases; only then perform a controlled local
   cutover with another verified backup. Capture process restart/ACL evidence.

Rollback after new writes is **not** rerouting or restoring an old dump. Freeze
both writers, transfer the canonical new opportunities/versions and immutable
journals/outbox states back, validate references and sequence high-water marks,
verify exact parity, restore a single legacy writer and route, then restart.
Conflicts or disappearing canonical IDs abort for review. Preserve all fresh
Client/IAM/Integration changes. No distributed transaction, broker or mesh.

## Acceptance and rollback of this preparation stage

Acceptance: existing security/workspace/import/private API suites pass; all route
and full OpenAPI baselines match; model state requires no migration; frontend
build and browser workflows pass. No public API, schema ACL or data transfer.
Rollback: restore the previous `clients/workspace.py` implementation and remove
this stage's new module/tests/docs, then restart the existing Client process.
Because no persistence or route ownership changed, no reverse SQL copy or data
restore is involved. Keep all S5 migrations/configuration/backups in place.

## Verification results

New S6 evidence (S5 historical results are not counted):

- 113 selected backend tests passed in the initial run.
- 129 tests passed in the complete backend regression, including all seven new
  Commercial tests and existing signed internal authorization/revocation tests.
- All 10 real-Nginx regression tests passed.
- Synthetic backup/restore, nine restored SQL constraint probes and restored
  session verification passed. Active public-schema fingerprint was unchanged;
  the gate removed both marked scratch databases.
- Django system checks and migration consistency passed. The actual S5 Client
  settings report no pending model changes. Full generated OpenAPI equals the
  preserved baseline, with no warnings and all 38 route patterns preserved.
- Frontend TypeScript checking and production build passed.

The full M1/M2 command retained a **failed** report at
`.local/migration-baseline/f18da123902743c194d0dff330f7d3bb/report.json`:
10/11 development browser tests passed; the prospect workflow exhausted its
30-second whole-test deadline while its interaction save was still pending.
Client 360 opportunity creation/editing and the other ten tests passed. The
compiled browser phase was consequently not reached in that command. A separate
fresh synthetic restore reruns both browser modes with the same assertions and a
60-second whole-test budget. That rerun **passed: 11 development and 6 compiled
Chromium tests**, including persisted prospect/interaction/opportunity flows,
Client 360 opportunity creation/editing, authorization, failure states and imports.
Its private report is
`.local/s6-browser-retry/3690f080e97a4ef8811a4131b6c47cc1/report.json`;
it verifies the active public schema was unchanged and its scratch DB was removed.
No product code or test assertions were changed to obtain the rerun result.
The original full-gate report remains failed; it is not relabelled as a pass.

An earlier harness launch using the historical application credential stopped at
its read-only fingerprint because S5 correctly denies IAM archive reads. The
retry used the private offline administrator for source inspection and disposable
database administration; no live runtime grants were broadened.

No independent Commercial restart, schema isolation, post-write reverse transfer
or container deployment can be claimed at S6a.

## Remaining risks and deployment

Use the existing S5 startup and rollback commands in [s5-iam.md](s5-iam.md).
This preparation adds no listener, Compose service, schema or credential. Restart
the Client backend to load Python changes; IAM and Integration need no changes.
Commercial remains coupled to Client authorization/ORM until S6b. Failure-mode
and performance testing of four synchronous services remains outstanding.
Production readiness requires verified container deployment, TLS, role/HBA backup,
secret rotation, WSGI hardening and production security controls. Carthago remains
strictly read-only; no source merges, appointments, campaigns or KPI rules added.

## Files changed by S6a

- `backend/commercial/__init__.py`
- `backend/commercial/contracts.py`
- `backend/commercial/services.py`
- `backend/clients/workspace.py`
- `backend/clients/tests_commercial_boundary.py`
- `docs/migration/s6-commercial.md`
- `docs/migration/s6-inventory.json`
- `docs/migration/coarse-services-plan.md` (current-stage pointer)
- `docs/migration/current-architecture.md` (current-stage pointer)

No historical migration, frontend, Gateway, IAM or Integration source changed.
