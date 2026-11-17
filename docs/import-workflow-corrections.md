# Safe import review corrections

Implementation basis: `data-import-workflow-review.md`. The investigation remains historical evidence; this document describes the subsequent implementation.

## Workflow and contracts

The frontend route remains `/gestion-donnees`. Examiner and successful upload now scroll the selected review panel into view and focus its accessible region on desktop and mobile, including repeated selection. Existing upload/history navigation remains available. The import is named by source type, source date and UUID: the original filename is not retained and is not invented. Loading, errors, validation totals, rejected-row filtering/CSV, compatible rule, publication blockers and explicit review actions remain in this panel. Published confirmation includes snapshot count, reviewer identifier and publication timestamp, with immutable journal history below.

A failed or refreshing preview disables publication, including an already open confirmation dialog. Rule-list pagination or failure no longer determines whether the independently loaded batch matching result is valid. Independent server-side permission and uploader/reviewer checks remain mandatory on publication.

Existing APIs and status values are preserved. `GET /api/imports/{organization}/batches/{batch}/` adds optional `policy_match.detail_code` for pending, revoked, date-format, schema and source-type differences while preserving `status=missing`. Invalid approved-key results include `configuration` for explanation, while `policy` stays null so they cannot become automatic usable suggestions. No candidate key is selected automatically. Missing-key validation no longer also produces the false generic claim that no approved rule exists.

`GET /api/imports/{organization}/policies/?view=operational|synthetic` adds compatible list views for approved active rules, filtered before pagination on the authorized organization. Existing approved, pending and historical views remain. Historical/test rules are not reclassified, approved, deleted or activated. Publication still uses the existing explicit `POST /api/imports/{organization}/batches/{batch}/publish/` contract.

New staged identifier warnings are limited to the same organization, source type, schema version and declared usage. Historical staging/snapshots are not rewritten. Warning matches are not client identity matches.

No database migration, Compose change, service extraction, identity merge, source-to-client projection or business approval is included.

## How an authorized user publishes

1. Open Gestion des donnees, choose the authorized organization and the import tab.
2. Upload a compatible XLSX with the correct source model, source date, date format and truthful usage classification. This validates and saves staging only.
3. A different authorized reviewer signs in and clicks Examiner for that pending import. The detail panel is immediately focused.
4. Inspect totals, rejected rows, their reasons and the CSV report. Correct and upload another file when necessary. An entirely invalid file cannot be published.
5. Inspect the matching approved configuration and all publication blockers. If missing/pending/revoked/incompatible, stop and obtain the required independent business/rule approval. A test rule is not operational approval.
6. Click Examiner la publication. For classified files, the validated approved rule is suggested; legacy configurations require deliberate manual selection and do not establish operational approval. Explicitly consent to excluding rejected records, if appropriate.
7. Confirm publication explicitly. Verify snapshot count, reviewer, timestamp and journal history. Publication creates immutable source snapshots, not editable CRM clients or securities accounts.

## Business gates and release risk

See `import-publication-approval-proposals.md` for physical-person and securities-account approval-ready proposals. Neither is active. Source keys, date configuration, publication policy, reviewers, visibility and any later client/account relationship rules need AMEN INVEST approval. Existing unclassified test configurations do not supply that approval. No upload is automatically approved or published.

S16.1 remains OPEN: intermittent full-suite opportunity-pipeline HTTP 503 is unresolved. Diagnostic instrumentation, four-second budget, authorization checks and fail-closed behavior are unchanged. A passing run does not establish a fix.

## Verification

Results are recorded below after execution against the isolated Docker stack; synthetic workbooks only. No main-stack business records are uploaded, approved or published by these tests.

Changed files for this increment:
- `frontend/src/features/imports/DataManagement.tsx`: accessible review focus, accurate blockers, safe publication controls and rule views.
- `frontend/src/lib/workspace-api.ts`: additive matching metadata types.
- `frontend/e2e/import-dashboard.spec.ts`: responsive Examiner and failed-refresh/recovery tests.
- `backend/ingestion/matching.py`: bounded organization-scoped matching diagnostics and invalid-key configuration explanation.
- `backend/ingestion/services.py`: scope/schema isolation for new warning lookups.
- `backend/ingestion/views.py`: approved operational/synthetic rule list views.
- `backend/ingestion/tests.py`: diagnostic-state and warning-isolation tests.
- This report, the approval proposal document, and links in `mvp-backlog.md` / `functional-gap-analysis.md`.

Executed verification on Docker Engine 29.9.3 / Compose 5.7.0, isolated gateway `http://127.0.0.1:5188`:
- Final full Chromium run: **46 passed, 1 skipped**, 4.3 minutes, scale scenario enabled. The skip is the existing development-only reference screenshot scenario on a compiled build. Desktop/mobile Examiner focus/visibility and failure/recovery of an actionable staging record both passed.
- Earlier complete attempts retained: 43 passed / 2 failed / 1 skipped (overly strict position assertion and changed subtitle contract, both corrected); 45 passed / 1 failed / 1 skipped (new recovery fixture accidentally reused a previously published idempotent import). The final test uses a separate source date and requires a newly created staging response. No HTTP 503 retry was added, and no application failure was marked expected.
- Browser coverage includes all three supported synthetic workbook types, reuse of approved rules for subsequent compatible imports, rejected-record exclusion consent, independent publication, history, visibility, revoked permissions, real dependency outages and recovery. Source-to-client projection remains disabled.
- Integration and PostgreSQL processes actually restarted: all three published workbook previews remained identical, including validation, source values and provenance. SQL checks confirmed exact fixture cells/digests/date normalization, immutable snapshot counts, independent uploader/reviewer and one publication journal/outbox per batch.
- Security/integration verification: passed; includes actual restricted SQL credentials and four migration histories, forged/replayed signatures, fresh revocation, transactional guarantees and federated audit delivery.
- Public-route check: 52 routes / 65 method-path pairs; unauthenticated operations and retired routes denied; OpenAPI compatibility preserved.
- Compose validation: all 8 supported configurations passed, with distinct test volume/project/credentials. This is additional configuration validation, not the basis for the container-runtime verification above.
- TypeScript and Vite compiled successfully inside the frontend image. No migration was introduced.

Private, excluded evidence: `.local/compose-test/s161-import-workflow-release-validation-20261116/`, the two earlier diagnostic archives, `regression-report.json`, `integration-report.json`, `routes-report.json`, `import-dashboard-sql.json`, and `import-dashboard-restart.json`. Synthetic desktop/mobile review screenshots are under `.local/ui-review/screens/import-review-*.png` and were visually inspected for the mobile view.

These results verify the synthetic import workflow, not production readiness. S16.1 remains unresolved even though the pipeline scenarios passed in these executions.

Final-image backend regression rerun: **244 passed** (208 general/contracts, 5 IAM, 13 Integration, 18 Commercial), all four suite exit codes zero. Security verification contained 15 passing checks; the source SQL verification contained 4 passing check groups.

Main stack rebuilt with `docker compose up --build -d`, followed by `docker compose restart gateway` to refresh upstream DNS after backend recreation. Both main and test inventories passed: seven healthy containers, four distinct Django processes, internal DNS, separate restricted credentials and gateway-only published application port. Main `/gestion-donnees` returned HTTP 200. No main-stack business upload, rule approval/revocation, snapshot publication or source mapping was performed. Existing database volumes were retained.
