# S5 - Independent Identity & Access Management

> Later status: [S6b is now verified locally](s6b-commercial.md). This document preserves the earlier phase and its evidence.


## Scope and verified deployment

S5 extracts IAM from the existing Django/DRF implementation. It does not extract
Client/CRM or Commercial. The local synthetic application keeps its Nginx entry
point at `http://127.0.0.1:5173`. IAM and Data Integration run independently;
Client/CRM and Commercial still share the compatibility backend.

This is a local development result, not production readiness. Docker CLI 29.9.3 is installed outside PATH, but its Engine is unreachable
(the `docker_engine` named pipe is absent).
Compose configuration validation passed with synthetic env files; images were not
built and containers were not executed. No production database
or real Carthago connection was accessed.

The prior decomposition and [S4 inventory](s4-inventory.json) were inspected before
implementation. See [the S5 ownership inventory](s5-inventory.json) for the actual
tables, migration lineages, routes and credential checks.

## Processes, responsibilities and public compatibility

| Process | Local port | Responsibilities |
|---|---:|---|
| Nginx Gateway | 5173 | Existing browser origin and compatible API routing |
| Compatibility backend | 8000 | Client/CRM, Commercial, platform schema/health and public audit federation |
| IAM | 8001 | Users, roles, memberships, authentication, sessions, login budgets, signed IAM contracts and IAM audit |
| Data Integration | 8002 | Existing isolated staging, snapshots, publication and import history |
| Vite | 5174 | Existing React application; no product source changes |

The independent IAM default manual command uses port 8003; the existing local
supervisor deliberately reuses the former private facade port 8001. Gateway
requests and Integration's IAM calls now reach the owned IAM application there.
The old facade is no longer the active identity authority.

Ten existing public route patterns move to IAM:

- `/api/session/`
- `/api/auth/csrf/`, `/api/auth/login/`, `/api/auth/logout/`, `/api/auth/access/`
- `/api/organizations/{organization_id}/users/`
- `/api/organizations/{organization_id}/memberships/{membership_id}/`
- `/api/organizations/{organization_id}/role-assignments/`
- `/api/organizations/{organization_id}/role-assignments/{assignment_id}/`
- `/api/organizations/{organization_id}/roles/`

The nine Integration routes remain on Integration; the other nineteen public
patterns remain on the compatibility backend. All 38 public patterns and 47
method/path pairs remain intact. Request/response serializers, session cookie
names, CSRF rotation, delegation restrictions and deny-by-default policies are
reused. The entire generated public OpenAPI document matches the M1/M2 baseline,
including authentication schemes, operation IDs, parameters and response schemas.
Private contracts are excluded from that document.

The bounded Audit module remains distributed across local transactional journals.
`/api/audit/` stays on the compatibility backend and federates its business journal,
IAM and Integration over signed HTTP. This avoids moving business audit writes
into a remote transaction. It preserves the existing public route and immediate
visibility without extracting an additional Audit service.

## Data ownership and migrations

`aiced_iam` owns 21 tables:

- Sixteen identity/authentication tables: `identity_user`, its two Django M2M
  tables, `identity_organization`, `identity_membership`, `identity_capability`,
  `identity_role`, `identity_role_permissions`, `identity_roleassignment`,
  `identity_loginbucket`, `identity_internalnonce`, `django_session`,
  `django_content_type`, `auth_permission`, `auth_group`, `auth_group_permissions`.
- `audit_auditevent`, `audit_auditoutbox`, `audit_auditreceipt`.
- `iam_control_runtimestate` and its own `django_migrations` recorder.

All IAM SQL foreign keys target IAM's own schema. The IAM deployment registers
no Client, Commercial, ingestion or Integration-store business models.

The original identity and audit model/service implementations are reused with
independent IAM migration modules under `iam_service/migrations/`. The original
public migrations and recorder remain preserved. IAM's new lineage installs the
existing revocation/append-only/outbox integrity rules and a writer fence.
It does not fake the historical monolith migrations as its owned lineage.

Five compatibility tables are added in `public`: actor, organization and membership
references, an owned nonce store, and the IAM journal-ID registry. These contain
stable validated UUIDs and minimal labels, not passwords, role definitions,
sessions or cached authorization. Initial users/organizations/memberships are
copied exactly and membership identity/org equality is checked. A signed,
delegated reference-validation contract supports subsequent membership validation.

Client party organization/assignee, CRM editor, interaction/opportunity author,
and business audit actor/org foreign keys now target these local references.
The composite assignee/organization constraint remains enforced. Reverse transfer
materializes references for IAM-only users before copying their audit events.
Historical immutable author/org references survive deactivation.

The consumer migration packages reuse the immutable historical modules through
their package paths and add only the S5 boundary migrations. IAM model registration
in the compatibility process is retained for that historical migration graph and
the composed public schema. It grants no SQL access: the running consumer role
cannot read or write either active IAM tables or legacy identity/session archives.
Removing that historical registration belongs to the later Client extraction.

The sixteen original public IAM tables remain as inactive archives owned by a
NOLOGIN role. The retired application credential loses their privileges. No
client, account, opportunity, import history or migration table was deleted/reset.
Retired ingestion archives keep their historical local FKs; they are not active
service dependencies. No active business FK points into `aiced_iam`.

## Credential and startup boundaries

IAM has a NOLOGIN schema owner, a separate NOINHERIT migrator that can assume only
that owner, and a runtime without memberships, SUPERUSER, CREATEDB, CREATEROLE,
REPLICATION, BYPASSRLS, schema CREATE, public-schema USAGE or database TEMP.
Runtime access is limited to its own tables/sequences. Journals/receipts are
append-only, control/migration tables are read-only, and immutable outbox identity
is protected by triggers. Role-capability removal participates in the S2 barrier.

The compatibility runtime also receives a new restricted credential: it retains
its business tables and local references, but no identity/session archive access
and no IAM/Integration schema access. Integration keeps its S4 credential.
Actual LOGIN connections test foreign SELECT and INSERT denial, and wrong
passwords are rejected by SCRAM authentication. Unneeded retired Integration and
central receipt archives are also inaccessible to the business credential. Application
connection hooks refuse unsafe runtime roles rather than silently using the old
database account. Offline migration flags must never enter runtime env files.

IAM retains the original Django signing secret so existing database sessions and
login budget keys remain valid. The compatibility process receives a new secret;
Integration retains its separate secret. Database credentials are never shared.
The compatibility process receives only its own client signing identities, not
Integration's or IAM's outbound signing keys.

## Signed internal contracts

All protected private requests use S2 HMAC binding of method, path, audience,
timestamp, nonce and body. Replay records are stored in the receiving service's
own database tables. Browser user/role headers are never identity proofs.

| Contract | Consumer / behavior |
|---|---|
| `POST /internal/v1/principal/resolve` | Existing Integration/peer delegated session validation |
| `POST /internal/v1/authorization/check` | Existing audience-limited fresh capability checks |
| `POST /internal/v1/grants/snapshot` | Client residue / future Commercial; bounded fresh self grants, scopes and org labels; no client decisions |
| `POST /internal/v1/references/validate` | Client; validates up to 100 active same-org memberships under delegated organization-wide client visibility |
| `POST /internal/v1/sessions/revoke` | Signed peer + POST credentials and original CSRF; revokes only the delegated user's own session, atomically audited |
| Existing `/internal/v1/imports/{context,audit-scope}` | Integration grants, UI flags and audit org scope |
| Existing `/internal/v1/integration/ready` | Signed Integration machine probe, same-database check |
| `POST /internal/v1/iam/audit/query` | Client audit federation; fresh audit grants, org filtering before count, bounded keyset chunks |
| Existing `POST /internal/v1/audit/events` | Producer-authenticated, idempotent outbox receipt |
| `/health/ready` | Minimal owned IAM DB/control readiness; no credentials exposed |

Permission mutations remain authoritative at the existing IAM user/membership/
role-assignment public APIs, with the same user session, CSRF and delegation
checks. There is no trusted service-header shortcut to change another user's
permissions. Administrative deactivation remains the existing audited Python
service boundary; no new public administration route was invented. Permission
definition edits are not a new frontend feature in S5.

Client/Commercial object filtering still resides in `clients/policies.py` and
workspace services. IAM supplies grants and membership identifiers; it never
receives client financial data to decide which clients are visible. Commercial's
future object-authorization contract remains hosted by the owning business
runtime, outside IAM's URLConf, with local replay protection and signed delegation.
A separate Commercial peer is not deployed or advertised as operational in S5; its
ingress key policy and contract tests must accompany that later extraction.

## Revocation and audit consistency

No positive authorization is cached across requests. The consumer validates the
session through IAM, then obtains fresh grants for its own SQL object filters.
For writes it acquires its local organization lock, the shared S2 transaction
admission barrier, and revalidates session/grants after waiting. IAM revocations
take the exclusive barrier. Both live on the same PostgreSQL database, as S2
requires; separate schemas/credentials do not defeat this coordination.

A revocation commits after already admitted writes finish. A queued write must
see the committed revocation before changing data. IAM authorization readers do
not take the exclusive barrier or business row locks, avoiding HTTP lock cycles.
User/organization deactivation, password/session changes and role/permission
changes also retain database revocation triggers. There are no bearer/JWT tokens
in the existing application; session deletion/hash validation provides revocation.

IAM's local mutation, required audit and outbox share one database transaction.
Request admission includes session persistence. Normal denied login responses
still commit login-budget consumption and denial records; server failures roll
back request state. Business writes and their local required audit/outbox remain
in the business transaction. No HTTP delivery runs inside a business transaction.

IAM/network errors deny protected business/import requests without stale grants
or a legacy fallback. Internal calls have bounded deadlines. The public Gateway
keeps its existing upstream error behavior. Public audit fails closed on a missing
journal; it never reports a partial successful audit page. Local immutable events
and pending outboxes remain durable if delivery is unavailable. Existing delivery
is retryable/idempotent; automatic scheduling of all business/IAM outboxes is not
introduced by this increment.

## Cutover, backups and rollback

The guarded tools accept only the existing DEBUG/loopback portable database or
marked disposable restores. They are not production migration commands.

1. Verify a full backup by restoring it before any ownership changes.
2. Stop the supervised local deployment, verify all its listeners are closed, and
   take/restore another backup. There is a deliberate maintenance interval.
3. Apply independent IAM migrations and additive reference/boundary migrations;
   copy original UUIDs, password hashes, sessions, budgets, roles and audit data.
4. Validate references, foreign keys and constraints. Fence old credentials;
   activate the owned IAM gate, switch compatible Gateway routes and start the
   independent processes. Verify authentication and business/import behavior.
5. Rehearse and actually exercise reverse transfer after new IAM writes, make new
   legacy IAM writes, then forward again and verify revocations survive.

Copies are offline administrator operations under exclusive cutover/revocation
locks. Journals are never updated on collision; conflicting immutable events
abort. Sessions and canonical permission/M2M sets replace the inactive copy,
including deletions. Union-only copying would resurrect removed grants and is
explicitly prevented. Disappearing canonical identity IDs require reviewed
reconciliation; they are not silently resurrected or deleted. Sequence high-water
marks never move backwards. New identities and audit actor references survive
repeated reverse transfer.

Backups verify table values/counts, columns, FKs/constraints, indexes, triggers,
functions, sequence state, owners and effective table/column/schema/function/
default privileges. Database-level ACLs are captured and reapplied on the marked
restore, since plain `pg_dump` without `--create` does not restore them. Cluster
roles must already exist; backing up global roles/HBA/TLS for another host remains
an operational prerequisite. No restore overwrites the application database.

Private active artifacts and backups remain ignored under
`.local/s4-active/b1cb997fda7f49a4a6331979c656bfb6/`. No secrets are in this document.

```powershell
$deployment = '.local/s4-active/b1cb997fda7f49a4a6331979c656bfb6'

# Full supervised local startup; do not also start duplicate manual listeners.
python scripts/run_s4_deployment.py --directory $deployment

# Independent IAM manual startup, alternative to the supervised IAM process.
python scripts/run_iam.py --env-file "$deployment/iam-env.json" runserver 127.0.0.1:8003 --noreload

# Owned migrations, offline migrator only.
python scripts/run_iam.py --env-file "$deployment/iam-migration-env.json" migrate --noinput

# Full repeatable restored rehearsal; never modifies the active database.
python scripts/s5_rehearsal.py --confirm-local-rehearsal

# Coordinated post-write rollback; stops/restarts the local deployment itself.
python scripts/s5_local.py --directory $deployment --confirm-local-cutover --rollback
python scripts/s5_verify_local.py --directory $deployment --phase rollback

# Forward again, carrying new legacy writes and preserving revocations.
python scripts/s5_local.py --directory $deployment --confirm-local-cutover --forward
python scripts/s5_verify_local.py --directory $deployment --phase final
```

`s5_verify_local` stages explicit synthetic test users and stores its password/
session evidence privately; its later phases depend on that staged evidence.
Run the continuity phases within the normal 30-minute session lifetime. It is
not a general production health check. Initial cutover requires
`--verification-report <passed-report>` and refuses a pre-existing IAM schema.
Recovery from a partially failed initial preparation requires review, not a
blind retry. Failures leave the deployment stopped rather than restart stale
writers. Do not roll back merely by changing Nginx or source code.

S4 rollback must follow S5 rollback; the tool rejects the reverse order. Restore
S4's Integration service before forwarding S5 again. The old `.local/postgres`
credentials/startup describe the historical backend and are not the S5 runtime.

For containers, use `docker compose -f compose.yaml -f compose.s5.yaml ...`, not
the S4 overlay simultaneously. Provision/copy/review ownership first. Private
`.env.iam-runtime`, `.env.iam-migrator`, `.env.iam-consumer`, `.env.integration`
and CA/server certificates under `.local/s5-tls` must be supplied securely.
No database/secret/TLS material is fabricated or committed. IAM uses internal
TLS 8443, Integration 8444, with no additional published application ports.
The Compose configuration was validated with isolated synthetic env files and
absolute build contexts, without starting containers. These development WSGI
listeners and the container deployment are not production-verified.

## Verification evidence

Private logs/reports contain reproducible evidence; references below are not
public datasets and must not be committed.

| Verification | Result |
|---|---|
| Existing backend regression | 122 tests passed; also rerun in the complete M1/M2 gate |
| Complete M1/M2 gate | Passed: backup/restore, nine constraint probes, 10 real-Nginx tests, frontend build, 11 dev and 6 compiled Chromium tests; original DB unchanged and scratch DBs removed |
| Final private/public contract tests | 18 passed with native Python exit 0 |
| Isolated IAM tests | 5 passed, including owned migration graph, absence of business models/routes and bounded private inputs |
| Integration tests | 8 passed with its actual restricted runtime configuration |
| Migration consistency | IAM and compatibility consumer report no model changes |
| Public contract | Entire OpenAPI object equals preserved baseline; no private paths or schema diagnostics |
| Real S5 security | Separate IAM/business/Integration/Nginx processes; foreign reads/writes denied, IT and cross-org denials, forged headers, signatures/replay, permission changes and session/user revocation |
| Transactions/concurrency | IAM and business required-audit failures roll back mutations; revocation overtakes a queued business write; removed role capabilities remain removed after reverse/forward |
| Session continuity | Pre-cutover session survives transfer; revoked session stays invalid through rollback/forward; independent IAM restart preserves an existing session |
| Actual local cutover | New IAM users/grants, revocation, audited history, post-write rollback, new legacy user, forward and unchanged Client/Integration domain hashes verified |
| Restore | 71 tables restored; extended function/default/database ACLs verified; IAM starts separately on restored data and accepts the valid session while refusing the revoked one |
| Browser | Existing React login and Panorama run against separate IAM and Gateway; screenshot retained privately |
| Safety tooling / Compose | 17 tooling tests passed; three Compose files parsed and the S5 Compose configuration validates; Docker Engine execution unavailable |

M1/M2 evidence: `.local/migration-baseline/ad738f3cd11047e290efb80b12af1bc2/report.json`.
The final S5 rehearsal reference and actual inventory are recorded in
`s5-inventory.json`. Local HTTP, restart, backup and ownership evidence is stored
beside `s5-state.json`. Earlier failed rehearsals remain available: an overly
broad test-role choice, browser harness selectors/root, and archive-owner schema
USAGE were corrected. A canonical M2M-copy issue found during review was fixed
and exercised with real permission removal. A final restore check initially used
a fixture that had naturally reached its 30-minute expiry; it was repeated with
a fresh authenticated fixture and also explicitly verified expired-session denial.
No expiry, authentication or migration check was bypassed to report a pass.

## Remaining limits and next increment

- Production backup approval/retention/RPO/RTO, global-role/HBA recovery, TLS and
  container execution, secret rotation, hardened WSGI supervision, monitoring and
  capacity/failover/security testing remain outstanding.
- The global revocation barrier assumes the same PostgreSQL database/instance;
  readiness is not a substitute for topology/HA verification. IAM is a deliberate
  synchronous availability dependency; there is no stale authorization cache.
- Grant/reference payloads and audit page deadlines are bounded. Large tenants
  need a reviewed paginated contract; deep live audit pages may return 503 instead
  of partial results. Nonce retention and worker scheduling also need operational
  configuration. No load/latency production claim is made.
- Historical IAM archives, public migration history and business journals remain
  intentionally retained. Removing archives requires a separate retention decision.
- Client/CRM and Commercial remain one runtime with local references and business
  object scopes. Their subsequent extractions require their own review/rehearsals;
  they have not been started here. Analytics/Reporting remains unimplemented beyond
  the existing UI behavior, and AI is future work.
- Carthago remains strictly read-only. No authoritative identity/account updates,
  automatic merges, real connector, field mapping, KPI rules, campaigns or
  appointments were introduced.

## Changed source files

- `backend/iam_service/`: settings, entry point, WSGI/TLS development listener,
  public/private contracts, isolated identity/audit migration lineages and tests.
- `backend/iam_control/`: owned cutover state, admission and SQL writer/revocation/
  immutable-audit migrations.
- `backend/iam_consumer/`: restricted compatibility configuration, signed session/
  grant adapter, local references/nonces/journal registry, boundary migrations,
  schema authentication extension and retired-route fencing.
- `backend/identity/{policies,coordination}.py`: explicit remote consumer branch;
  original IAM policy/services remain authoritative in IAM.
- `backend/clients/{models,policies,workspace,services,prospects,workspace_views}.py`:
  local reference targets and business-owned object filtering; no service extraction.
- `backend/audit/{models,views,multi_federation}.py`: local actor/org
  references and bounded immediate three-journal federation.
- `backend/internal_api/views.py`, `backend/integration_service/{settings,private}.py`:
  remote delegation compatibility, private-schema exclusion and narrowly authenticated
  Client audit ingress with fresh IAM scope checks.
- `infra/gateway/{nginx.conf.template,start.sh}`, `backend/testing/gateway.py`,
  `scripts/{run_gateway,run_s4_deployment}.py`: optional compatible IAM routing and
  separately configured supervised IAM process.
- `backend/Dockerfile.iam`, `compose.s5.yaml`: independent deployment definition.
- `scripts/{run_iam,s5_database,s5_backup,s5_rehearsal,s5_local,s5_verify_local}.py`,
  `scripts/s5_browser.mjs`, `scripts/tests/test_s5_safety.py`, and the S4 rollback
  ordering guard: controlled copy, restore, isolation, rollback and verification.
- Migration report/inventory and current-status documentation. No React business
  source, existing migration file, private reference, secret or upload was committed.
