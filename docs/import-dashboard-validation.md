# Import review and home dashboard correction

Scope: existing four-service architecture, database ownership and Compose files
are unchanged. No database migration, new route, permission, automatic merge,
financial formula or direct cross-schema application access is introduced.

Read [the investigation and complete source-column proposal](import-source-mapping.md)
for workflow, persistence, supported types, validation, KPI definitions and
AMEN INVEST decisions. Publication is already functional; staging is deliberate.
The missing safe connection was the home screen's obsolete placeholder copy:
existing S16 reporting had not been integrated there.

## Files changed in this increment

- `frontend/src/features/dashboard/DashboardPage.tsx`: API mode uses live home;
  development-only illustrative mode retained separately.
- `frontend/src/features/dashboard/LiveDashboard.tsx`: authorized client count,
  existing CRM reporting, source/CRM explanation and financial unavailable reasons.
- `frontend/src/features/reporting/CommercialActivity.tsx`: optional embedded
  heading; same report logic, period, authorization and independent failure states.
- `frontend/src/features/imports/DataManagement.tsx`: explicit permission,
  separation-of-duty, rule availability and no-valid-row blockers; publication
  time, publisher, policy and immutable snapshot count. Backend remains authoritative.
- `frontend/src/lib/workspace-api.ts`: types existing published_by_id response field.
- `frontend/e2e/import-dashboard.spec.ts`: home counts/charts, source failure,
  three source-format UI uploads and publications, unauthorized uploader,
  no client creation, reload/history and mobile layout.
- `frontend/e2e/activity.spec.ts`: wait for responsive chart reflow before
  asserting the existing no-horizontal-overflow condition.
- `scripts/compose_browser.py`: generates three synthetic positional fixtures
  and private expected-cell/hash evidence; no reference records used.
- `infra/acceptance/import_dashboard.py`: read-only SQL assertion of each browser
  fixture, snapshots, dates, provenance, journal/outbox, no identity/account keys.
- `scripts/compose_import_dashboard_restart.py`: isolated Integration/PostgreSQL
  actual process restarts with identical existing-session payloads and SQL fingerprints.
- This document, mapping proposal, functional gap analysis, MVP backlog and open questions.

## Routes and APIs

Home `/tableau-de-bord`, report `/activite-commerciale`, import `/gestion-donnees`.
Home reuses GET `/api/clients/?page_size=1`,
GET `/api/clients/activity-report/?date_from=...&date_to=...&kind=...`,
GET `/api/opportunities/?page_size=1` and GET `/api/campaigns/?page_size=1`.
No new backend/public contract. A maximum of four business requests per initial
home load; query cache may reuse existing results. Manual report refresh requests
the three report sources; no unbounded client-side scanning or business polling.
Client-count errors hide previous values. Existing report error branches hide
failed-source counts, independently of successful sources.

Existing import API namespace `/api/imports/{organization_id}/`: upload,
batches list, batches/{id} preview/rejections/publish and policies create/approve.
Published source cells can be inspected through the authorized batch preview;
there is no newly invented ordinary-CRM source visibility policy.

## Reproduction on disposable synthetic test data

```powershell
docker compose -f compose.yaml -f compose.test.yaml up --build -d
docker compose -f compose.yaml -f compose.test.yaml restart gateway
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
$env:AICED_E2E_SCALE='1'
python scripts/compose_browser.py --test
Remove-Item Env:AICED_E2E_SCALE
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/import_dashboard.py
python scripts/compose_import_dashboard_restart.py --test
python scripts/compose_browser.py --test import-dashboard.spec.ts --grep 'Published synthetic'
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/imports.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
python scripts/compose_inventory.py --test
```

Run mutation/recovery/browser suites sequentially. Fixture generation occurs on
every browser runner invocation, so run SQL/restart comparison before a later
browser invocation replaces private expected fixtures. The fresh-visit test uses
the saved manifest only and creates no new imports.

## Results and limitations

Verification results are recorded below after execution. Evidence stays in
excluded `.local/compose-test/`; no credentials, customer rows or XLSX files are
committed. These local Docker checks do not establish production readiness.

- Docker Engine 29.9.3 was reachable. Compiled frontend TypeScript/Vite build passed.
- Backend regressions: 183 general + 5 IAM + 8 Integration + 18 Commercial =
  **214 passed**, no failures. This includes parser/date/deduplication/security,
  publication authorization, concurrency and rollback/immutable-record tests.
- Live import probe: **5 checks passed** (malformed/duplicate rows, rejection
  CSV, replay, distinct-user policy/publication, immutable snapshot).
- Live activity probe: **4 groups passed**, including authorized SQL/count
  comparison, IAM revocation and expiry; no report audit/outbox writes.
- Live security/integration probe: **15 groups passed**, covering actual schema
  credentials, four histories, CSRF, forged/replayed signatures, object
  reassignment/revocation and atomic audit/outbox failure rollback.
- Routes/OpenAPI: **50 routes / 63 method-path checks passed**; existing
  OpenAPI contract preserved. No new API contract or migration in this correction.
- Compose validation: **8 configurations passed**, independent test database
  volume and credentials; actual runtime inventory also passed seven healthy
  containers and four independent service processes.
- Initial full browser run: 35 passed, 1 failed, 1 intentionally skipped. The
  failure was the existing S16 responsive test reading width before Recharts
  completed resize; it now waits for the same assertion with a bounded poll.
  New home/source-workbook tests already passed in that run. Earlier test
  development also encountered Chromium response-body eviction; the harness
  now confirms upload HTTP status and reads the persisted batch via API.
- Exact three-template PostgreSQL comparison passed: all expected cells,
  digests, normalized dates, source dates, publisher/policy, one snapshot and
  one journal/outbox pair per publication. Source keys absent from CRM identity
  and account tables; browser verified CRM client count unchanged.
- Actual Integration and PostgreSQL process restarts passed: identical source
  API payloads using the same session, unchanged SQL fingerprints; fresh-browser
  history check passed afterward. No volume deletion or real-record import.
- Final full Chromium run: **36 passed, 1 intentionally skipped, 0 failed**
  (37 total, 3.8 minutes), including the 10,000-opportunity regression and all
  three new import/home/history tests. Full report/log archived privately as
  `import-dashboard-full-browser.json` / `.log`. The skipped test needs the
  development-only illustrative screen, unavailable in the compiled stack.
  SQL comparison and both actual restarts were repeated on these final fixtures;
  the fresh-browser published-history test passed again after restart.
- Main local stack rebuilt using unchanged `docker compose up --build -d`,
  then gateway restarted for service DNS. The real home browser check passed
  on port 5187; final inventories for main and isolated test each show seven
  healthy containers. No source uploads or policy approvals were performed on
  the main stack by this verification. Main dashboard:
  `http://127.0.0.1:5187/tableau-de-bord`; imports:
  `http://127.0.0.1:5187/gestion-donnees`.

Performance remains bounded by the existing S16 93-day report limit and
4-second processing budget, plus the existing linear/batched authorized
opportunity scan. The home adds no extra aggregation service or cache. It may
show a safe unavailable state if a source exceeds its existing resource budget.
There is no distributed snapshot across independently read service counters.
No source-to-CRM object mapping, financial balance, retention, approved business
segmentation, active campaign count or financial performance is delivered.
