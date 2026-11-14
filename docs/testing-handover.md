# AICED — Project handover and testing guide

> Current architecture: **S6b verified locally**. IAM, Client & CRM, Commercial and Data Integration run separately with restricted data ownership. All 38 routes are preserved; actual post-write rollback/forward, browser workflows and restore were verified. See [S6b report](migration/s6b-commercial.md). Container execution and production readiness remain unverified. Earlier phase status paragraphs below are historical.


**Current status: S5 (2026-11-14).** IAM and Data Integration are independently running in the local synthetic deployment with separate restricted schemas/credentials. All 38 public routes are preserved. Post-write rollback, forward cutover, restore and independent IAM restart were verified. Client/CRM and Commercial remain in the compatibility backend. See [S5 results, startup and rollback](migration/s5-iam.md) and [actual ownership](migration/s5-inventory.json). Docker and production deployment are not verified. Earlier status statements below are historical.

**Prepared:** 14 November 2026  
**Audience:** project teammates, developers and manual testers  
**Scope:** actual repository implementation and recorded verification results. This is a development MVP, not a production acceptance certificate.

## 1. Start here

On the prepared Windows computer, open **http://127.0.0.1:5173/connexion**. The program was started through Nginx, with Django on port 8000 and Vite on port 5174. These processes must be running for the link to work. On another computer, `127.0.0.1` refers to that computer; follow the setup instructions below.

Use `synthetic.operator.a` for the broadest business-feature walkthrough. Obtain its development password from the project owner through a private channel. On the prepared computer it is stored in `.local/postgres/seed-password`. **The password is intentionally excluded from this document and the shareable test package.**

Recommended first test: log in → open **Clients** → create an AICED client → edit its CRM profile → add an interaction and an opportunity → open **Prospects** → open **Gestion des données** and upload a supplied synthetic workbook.

Use only synthetic names, email addresses and files. Do not import the private reference Excel files or real customer information.

## 2. What has been added

| Area | Implemented behavior | Important limits |
|---|---|---|
| Backend foundation | Django REST Framework, PostgreSQL models/migrations, validation and API contracts | Existing migrations and records are preserved. |
| Authentication | Server sessions, login/logout, CSRF checks and login-attempt limits | Password recovery, SSO and MFA are absent. |
| Authorization | Explicit capabilities, organization and assigned-record scopes, financial-data restrictions, revocation checks | A manager or IT title does not grant every capability. Production role definitions still need business approval. |
| Connexion | Actual sign-in, validation, error feedback and return to the requested protected page | French interface; synthetic development accounts. |
| Tableau de bord | Shared navigation/layout and authorized client information | Full business KPIs, scoring and managerial analytics are absent. Development mockup previews are explicitly fictional. |
| Panorama Clients | Authorized search, filters, pagination and links to Client 360 | Prospects are deliberately listed separately. |
| Client 360 | Actual detail retrieval, provenance, CRM, source accounts, interactions and opportunities | Source identity/accounts are read-only. Documents and AI assistance are unavailable. |
| Manual AICED clients | Create physical/legal AICED clients; edit eligible AICED identity and CRM data | Cannot edit Carthago identity or attach/merge an unapproved source identity. |
| Prospects | Create/search/qualify prospects, next-action information, shared detail, interactions and opportunities | Status is manual. Next action does not create a calendar event or reminder. |
| Commercial activity | Create/edit completed interactions and opportunities | Opportunity amounts are commercial estimates in TND, with three decimal places, not source balances. Calendar/campaign workflows are absent. |
| Data Management | XLSX validation, staging, preview, row errors/warnings, CSV rejection report, history and reviewed publication | Publication creates immutable source snapshots only. It does not create/update clients or accounts. |
| Audit | Required audit/outbox records committed with business changes; signed, retryable delivery to the audit receiver | Consolidated visibility for a future live extracted service still needs its S4 cutover design. |
| Gateway | Single Nginx entry point; existing 38 public route patterns preserved | No service mesh, Kafka or Kubernetes. |
| Service migration | S1 decomposition/isolation preparation; S2 signed internal authorization and revocation/audit boundaries; S3 isolated Integration candidate | The target remains four coarse services. The default running application has not been switched to the candidate. |

The frontend uses React, TypeScript, Vite, Tailwind, Router, Query, RHF/Zod and Recharts. Existing screen designs were compared with rendered PDF mockups in earlier implementation phases. No pixel-perfect or complete accessibility certification is claimed.

## 3. Test accounts and permissions

These accounts were queried in the running application's database. All eight accounts below were active at inspection. The operator password was separately checked against the stored hash. Other account passwords were not rechecked for this handover; seed commands do not overwrite an existing password.

| User type | Account | Scope and useful tests | Expected restrictions |
|---|---|---|---|
| Operator | `synthetic.operator.a` | Organization A: create/edit AICED clients and CRM, manage prospects/interactions/opportunities, view source financial data, upload XLSX and propose rules | Cannot approve/publish imports; cannot manage users through its current grants. |
| Reviewer | `synthetic.reviewer.a` | Organization A: client/financial read access, inspect imports, approve/revoke rules and publish another user's batch | Cannot upload, propose rules or edit CRM with its current grants. |
| Manager | `synthetic.manager.a` | Organization A: client and financial read access, CRM updates, user/grant administration and audit consultation | No implicit import, prospect, interaction or opportunity permissions. |
| Portfolio user / Reader | `synthetic.reader.a` | Assigned clients in organization A; CRM updates on those clients | No financial, import, prospect or user-administration access. Despite its name, this role can update permitted CRM data. |
| IT administrator | `synthetic.it.a` | User/grant administration in organization A | No client or financial-data access. Cannot delegate capabilities it does not hold. |
| Other-organization users | `synthetic.reader.b`, `synthetic.manager.b`, `synthetic.it.b` | Equivalent roles in organization B; use to test A/B isolation | Organization A must remain inaccessible. |

User administration and audit have backend APIs; there are no dedicated complete administration/audit frontend pages in the current React routes. Use the API or automated tests for those areas.

The operator has a separate prospects role in addition to its workspace role. A user's effective permissions are the combination of active grants, their scope, organization and expiry. Django staff/superuser flags do not automatically grant business-data access.

## 4. Architecture: what the tester is actually using

**Default application:** Browser → Nginx Gateway → existing Django backend → existing PostgreSQL tables. The SPA uses relative `/api/` requests. IAM, Client/CRM and Commercial have not been independently extracted.

**S3 candidate:** a separate Django/DRF entry point with its own migrations, restricted PostgreSQL credentials and the `aiced_integration` schema. It reuses the existing import/parser rules through adapters. IAM is contacted through signed private HTTP APIs; IAM/Client/Commercial models are not registered in the candidate.

The candidate owns copies of `ingestion_importpolicy`, `ingestion_importbatch`, `ingestion_stagingrow` and `ingestion_sourcesnapshot`, plus local actor/organization references, journal, outbox and migration recorder. All candidate foreign keys stay inside its schema. Runtime SQL access to IAM, Client and Commercial was tested and refused.

S3 was exercised through opt-in Gateway routing on disposable restored data. **No live table ownership or default import routing was transferred.** Earlier plan text referring to “10 import routes” is inaccurate: the frozen contract contains **9 import route patterns**, within **38 total public route patterns / 47 method-path pairs**.

The retained local candidate is a testing environment, not the default UI database. A direct candidate URL is not a replacement login page. Do not point the normal Gateway at it without coordinating the IAM database, source copy, jobs, credentials and audit behavior.

## 5. Starting on another development computer

### Preferred documented path: Docker Compose

Prerequisites: Docker Engine/Compose, repository access and an approved local environment. Docker was unavailable on the verification computer, so the Compose deployment itself has **not** been verified there.

1. Copy `.env.example` to `.env`. Generate independent development secrets for Django, PostgreSQL and Gateway; replace all placeholders. Keep `.env` private.
2. Run from the repository root:

```sh
docker compose build
docker compose up -d db
docker compose run --rm backend python manage.py migrate
docker compose up -d backend frontend gateway
```

3. Open `http://localhost:5173/connexion`. Check `/api/health/` returns HTTP 200.
4. For a new synthetic development environment, privately set `AICED_SEED_PASSWORD` and run:

```sh
docker compose run --rm -e AICED_SEED_PASSWORD backend python manage.py seed_synthetic --confirm-synthetic
docker compose run --rm -e AICED_SEED_PASSWORD backend python manage.py seed_workspace --confirm-synthetic
docker compose run --rm backend python manage.py seed_prospects --confirm-synthetic
```

Seeds require DEBUG development mode and explicit synthetic confirmation. They preserve existing passwords and do not automatically repair modified existing roles. Do not seed an environment containing real data.

### Without Docker

Use Python 3.12, PostgreSQL 17 and Node/npm compatible with the frontend lockfile. Install `backend/requirements.lock` and run `npm ci` in `frontend`. Export the database/Django variables yourself: Django does not automatically load `.env`. Set the database host to the actual local PostgreSQL host.

```sh
python backend/manage.py migrate
python backend/manage.py runserver 127.0.0.1:8000
# In a separate terminal:
npm --prefix frontend run dev
```

Vite normally serves port 5173 and proxies the API to port 8000. This direct development mode is useful for UI work; it does not verify Gateway behavior. For Nginx, use `scripts/run_gateway.py` with the same private Gateway key configured for Django, as described in `docs/migration/m2-gateway.md`.

On the already prepared Windows computer, `scripts/backend_check.py` loads `.local/postgres/env.json`; `scripts/local_postgres.py` can start its portable PostgreSQL cluster on port 55432. The `.tools/` and `.local/` directories are private local prerequisites and are not part of a normal clone.

Do not reset PostgreSQL, delete migration files or restore an old dump over newer records. Use a separate approved development database for automated tests and migration rehearsals.

## 6. Manual test checklist

Record PASS, FAIL, BLOCKED or NOT RUN for each case. A hidden button alone is not proof of server authorization. Advanced access tests should also request the endpoint directly.

| ID | Account / action | Expected result |
|---|---|---|
| AUTH-01 | Visit `/clients` while logged out, then sign in | Redirect to Connexion, then return to the requested protected page. |
| AUTH-02 | Submit wrong credentials or required fields empty | Clear error/validation; no authenticated session. Repeated attempts are rate-limited. |
| AUTH-03 | Log out, then reopen a protected URL or refresh | Authentication required; private content must not remain usable. |
| CLI-01 | Operator: search/filter/page through Panorama Clients | Relevant authorized results; no organization B records; working empty state for an absent synthetic name. |
| CLI-02 | Operator: create a synthetic physical or legal AICED client | New detail page appears; refresh preserves the record. Use a name such as `SYNTHETIC QA 2026-11-14`. |
| CRM-01 | Operator: edit email, phone, notes and other available CRM fields | Valid values persist; invalid email and excessive lengths are rejected. |
| CRM-02 | Open one CRM editor in two browser tabs; save tab A, then the old editor in tab B | Second save reports a version conflict; it must not silently overwrite tab A. Reload before retrying. |
| SRC-01 | Open an externally sourced client/account | Provenance and disconnected/source status are visible; source identity/accounts cannot be edited. |
| ACT-01 | Operator: create/edit a completed interaction | Subject, date and content persist after refresh. This is not an appointment booking. |
| OPP-01 | Operator: create/edit an opportunity | Title/status/notes persist; estimates remain TND commercial amounts; invalid/negative or overprecision values are rejected. |
| PRO-01 | Operator: create and qualify a prospect; set a next action/date | Prospect appears in Prospects and its detail page, not the normal client directory. No automatic reminder or conversion occurs. |
| SEC-01 | Reader A: open an assigned client, then another user's unassigned client | Assigned access works; unassigned object access is denied or hidden, including direct detail/account/activity routes. |
| SEC-02 | Manager B: request an organization A client UUID or import URL | No organization A content or counts are disclosed. |
| SEC-03 | IT: navigate directly to Clients/Data Management and request client/financial APIs | Access denied, even if a URL or UUID is known. |
| SEC-04 | Developer: attempt injected organization/source/owner/role fields in a business mutation | Unknown or protected fields are rejected; no privilege escalation. |
| SEC-05 | Developer: omit/change CSRF on a mutation; supply arbitrary `X-User-ID` or `X-Role` headers | Request denied; headers do not create an identity or permissions. |
| SEC-06 | Administrator/test harness: revoke a role/session or deactivate a user, then retry | Fresh requests are denied. UI permission labels may lag until refresh; the server remains authoritative. |
| IMP-01 | Operator: upload `01-legal-valid.xlsx` using the settings below | Staged batch, two rows, no row errors; no automatic client/account creation. |
| IMP-02 | Upload the exact same file again with identical metadata | Same batch UUID; no duplicate batch. Re-saving the workbook may change its bytes and is not the same replay test. |
| IMP-03 | Upload `02-legal-duplicates.xlsx` | One valid row and two duplicate-key rejected rows; inspect errors and download CSV. |
| IMP-04 | Upload `03-legal-wrong-headers.xlsx`, then `04-not-an-excel.xlsx` | Validation error; no partially staged batch for those invalid files. |
| IMP-05 | Operator: propose rule → Reviewer: approve → Reviewer: publish operator's batch | Snapshot count increases; batch becomes published; historical client/account identities remain unchanged. |
| IMP-06 | Try creator self-approval or uploader publication; try publishing rejected rows without exclusion | Operation denied/blocked. The current operator already lacks approval capability; automated tests also cover double-actor rules. |
| IMP-07 | Reviewer: explicitly exclude rejected rows, publish, then repeat publication | Only valid rows published; repeat has no additional snapshots. A revoked rule cannot authorize a new publication. |
| ERR-01 | Developer: stop Integration/IAM in the isolated candidate environment | Safe unavailable/error state; no fallback to stale grants or foreign ORM. Do not interrupt the shared demo while someone else tests it. |

Expected API error categories: **400** invalid input, **403** authentication/permission/CSRF denial, **404** missing or out-of-scope object, **409** stale version/conflicting state, **413** oversized payload, **429** quota/rate limit, **503** unavailable IAM authorization. A failed Gateway upstream can return **502/504**. Check error content as well as status.

## 7. Excel test settings and two-person publication

The shareable test package contains generated **synthetic-only** files. No private reference rows are included.

| File | Contents / expected result |
|---|---|
| `01-legal-valid.xlsx` | Exact legal-person template, sheet `Tier`, two synthetic keys/names; two accepted rows. |
| `02-legal-duplicates.xlsx` | One unique key and two occurrences of another key; both duplicate rows rejected. |
| `03-legal-wrong-headers.xlsx` | One altered header; whole-file rejection. |
| `04-not-an-excel.xlsx` | Plain synthetic text with an XLSX extension; whole-file rejection. |

Select **Tiers personnes morales**, **ISO** dates and **partial snapshot**. Use today's source situation date or a nonfuture date suitable for the test. The supplied workbooks have no date values. For a test publication rule choose key column **2 / B — Identifiant**, ISO dates and a meaningful justification of at least 20 characters. This is a synthetic snapshot rule, not approval of a real Carthago mapping.

1. Operator uploads and previews the file; note the batch UUID and digest.
2. Operator proposes the publication rule in **Règles de publication**.
3. Reviewer logs in separately and approves the operator's rule.
4. Reviewer opens the batch and examines publication. For the duplicate workbook, explicitly confirm exclusion of rejected rows.
5. Reviewer confirms publication. Refresh and inspect history; repeat publication to verify idempotency.

The three supported source templates are physical persons (`Tier`, 33 columns), legal persons (`Tier`, 25 columns) and securities accounts (`Compte titre`, 41 columns). Headers and positions are exact, including blank/duplicate labels and a trailing space in an account header. Do not rename columns or let Excel turn identifiers into numbers. Consult `docs/import-templates.md` before building other fixtures.

Default technical limits include 10 MiB compressed XLSX, 25 MiB expanded content, 50,000 rows, 20 staged batches and 50 new batches per day per organization. These are configurable. A quota warning after repeated testing is not necessarily a defect; do not delete audit history to clear it.

## 8. Automated verification and recorded results

Recorded runs on 14 November 2026:

| Verification | Recorded result | Scope |
|---|---|---|
| Final main-backend suite | **116 passed**, 43.000 s; process exit 0 | Identity, object isolation, client/CRM, imports, audit, contracts, service architecture and internal APIs. |
| Full M1/M2 safety gate | **Passed** | Synthetic backup/restore, preserved session, integrity probes, schema/migration checks, OpenAPI, frontend TypeScript/build. |
| Real Nginx regression suite | **10 passed**, 35.254 s | Gateway compatibility, authorization/error handling and communication. |
| Existing Chromium tests | **11 development + 6 compiled-bundle passed** | Existing UI flows through Gateway; compiled bundle served in a test environment. |
| Isolated Integration tests | **8 passed**, 0.254 s | Owned models/migration graph/routes, no foreign ORM, delegated job authorization, actor/scope checks and slow-response deadline. |
| S3 real-process rehearsal | **15 checkpoint groups passed** | Separate IAM/Integration/legacy processes, SQL credential isolation, all 9 import routes, revocation race, required audit rollback, failures/restart, outbox retry, backups/restores and pre-cutover routing rollback. |
| Candidate Chromium smoke | **3 scenario groups passed** | Login/restored snapshot preview, real upload/duplicate preview, permission-aware IT denial. |
| Safety-script unit tests | **11 passed** | Database-name/marker guards, cleanup ownership and precise constraint comparisons. |

Private evidence on the prepared computer:

- `.local/s3-backend-final-clean.log`
- `.local/migration-baseline/9279a04006aa43b7ad235e822690036f/report.json`
- `.local/s3-rehearsal/845cee4b452d4f81b6127e1d44ebe0b8/report.json`

The S3 report confirms the application database was unchanged by that rehearsal. Its retained candidate is separate, with processes stopped after verification. Normal UI use can subsequently change the development database; that does not invalidate the earlier recorded comparison.

Useful commands on the prepared Windows computer:

```sh
python scripts/backend_check.py check
python scripts/backend_check.py makemigrations --check --dry-run
python scripts/backend_check.py test core identity clients ingestion audit contracts service_architecture internal_api --noinput
python -m unittest discover -s scripts/tests -v
python scripts/migration_baseline.py --confirm-synthetic --gateway
python scripts/s3_rehearsal.py --confirm-local-rehearsal
```

The last two commands require the prepared local tools/private environment and create guarded disposable databases. They are not production migration commands. Avoid concurrent manual writes to the application while a gate is comparing its before/after fingerprints. S3's default rehearsal cleans its own scratch databases/roles; `--keep-candidate` retains its candidate intentionally.

On another development machine, run the equivalent explicit Django test labels using that machine's approved test database. The test account needs permission to create a disposable test database. **A bare Django test command from the repository root can discover zero tests; zero discovered tests is not success.**

## 9. What still needs to be added or approved

| Priority | Remaining work |
|---|---|
| Next architecture stage | Dedicated S3 operational handover/runbook completion and reviewed S4 Integration live cutover: freeze, approved backup, copy/parity, one writer, old jobs/ACL removal and safe post-write rollback. |
| Before Integration live cutover | Preserve immediate/scoped public audit visibility: current central receipts are not automatically the existing public audit listing. Decide/implement and test authorized federation or an approved freshness contract. |
| Service target | Independently extract IAM, Commercial and Client/CRM in later stages. Four independently deployed services are not yet delivered. |
| Commercial MVP | Appointments/calendar, reminders, campaigns and broader commercial workflows. |
| Analytics | Approved segmentation, KPI definitions and managerial reporting/dashboards. No invented scores or financial totals. |
| Integration approval | Real read-only Carthago access method, credentials, schemas/API contracts, field ownership, account/client mapping and automated synchronization. None is assumed or enabled. |
| Other product work | Reconciliation workflows, document attachments, notifications, AI assistance, password recovery, SSO/MFA and remaining reference screens. |
| Before production | Business role matrix, deployment/TLS/container verification, least-privilege rollout for remaining services, key rotation, backup RPO/RTO/retention, monitoring/outbox alerts, load testing and broader browser/accessibility testing. |

Docker Compose definitions exist, including the candidate overlay, but Docker/container networking and production TLS were not run on this computer. Actual S3 verification used separate local processes and PostgreSQL restricted logins. The private TLS listener and development servers are not a production hardening sign-off.

The shared database advisory barrier requires IAM and Integration to use the **same PostgreSQL database**. It provides revocation coordination across their local transactions without a distributed transaction. PostgreSQL failover/long network partitions and HA operation have not been verified.

**Carthago rule for every future change:** source identities, accounts and financial data remain read-only. Publishing Excel snapshots must never silently merge or overwrite authoritative records, and absence from an export must not delete a client.

## 10. Reporting a bug

Include the following, using synthetic data only:

```text
Test ID / short title:
Date and code version (commit if available):
Environment: normal app / S3 candidate / direct mode / Gateway
Browser and viewport:
Account role and organization (no password):
Page URL and synthetic record/batch UUID:
Steps to reproduce:
Expected behavior:
Actual behavior:
HTTP status and X-Request-ID, if available:
Screenshot / sanitized console or API error:
Reproduces after refresh?:
Severity: critical / high / medium / low
```

Unauthorized data access, privilege escalation, source-data modification, lost updates, missing required audit or loss/duplication of published data are high-priority findings. Never attach session cookies, CSRF tokens, private keys, `.env`, database dumps or real customer data to a shared issue.

Suggested sign-off: record the test environment and role for every case; explain each FAIL/BLOCKED/NOT RUN; link sanitized evidence; identify who reviewed unresolved risks. Passing the smoke walkthrough does not imply production readiness.

## 11. Repository map and reference documents

| Path | Purpose |
|---|---|
| `frontend/src/features/` | Authentication, dashboard, client/CRM, imports and prospects screens. |
| `frontend/src/lib/` | API clients/contracts; screens keep existing same-origin calls. |
| `backend/identity/` | Users, organizations, roles, capabilities, sessions and IAM services. |
| `backend/clients/` | Client/CRM, prospects, interactions and current opportunity implementation. |
| `backend/ingestion/` | Shared parser/templates/import business rules and default deployment adapter. |
| `backend/integration_service/` | Separate candidate settings, entry point, delegated IAM access, audit delivery and URLs. |
| `backend/integration_store/` | Candidate-owned models, two migrations, tests and outbox command. |
| `backend/internal_api/`, `backend/core/admission.py` | Signed private contracts and shared revocation coordination. |
| `backend/audit/` | Existing central/local audit functionality and receipt/outbox handling. |
| `infra/gateway/`, `compose*.yaml` | Gateway and development deployment definitions. |
| `backend/contracts/public-api-baseline.json` | Frozen public routes and historical migration baseline. |
| `docs/migration/coarse-services-plan.md` | Current service decomposition and S1–S7 order. |
| `docs/migration/s2-authorization-audit.md` | Signed auth, revocation, audit consistency and extraction prerequisites. |
| `docs/import-templates.md`, `docs/open-questions.md` | Exact Excel schemas and unresolved business/integration decisions. |

Older phase reports are historical snapshots; their smaller test counts and “not implemented” statements can predate later work. Use this guide's dated status together with the current code and newest verification evidence.
