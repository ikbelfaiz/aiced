# S16 - Source Mapping and Client 360 Integration Preparation

This milestone name follows the current request, independently of the earlier
S16 Commercial Activity Reporting evidence, which is preserved.

## Delivered scope

Approval-ready [field/ownership matrix](source-mapping-approval-matrix.md) covers
all 99 positional columns (including three blank columns), relationship
cardinalities, ambiguity, null/duplicate handling and required sign-offs.
[Contract and visibility document](source-mapping-contract.md) separates the
working synthetic protocol from the proposed, unregistered real-source API.

Client 360 `/clients/{id}` now includes **Rapprochement source - preparation
synthetique**. Opening the demo requests
`GET /api/clients/{id}/source-mapping-preview/?scenario=...`.
No new frontend route. Cases: unique candidate, physical/legal namespace
ambiguity, missing identifier, duplicate account key, one fictitious client
with two accounts, conflicting D/AH references. Every match is labelled a
candidate; `confirmed`, `mapping_approved`, `real_source_access` and
`relationships_persisted` are false. Source keys, validation and fixture
provenance are inspectable. The illustrative `SYNTH-CRM-*` is explicitly
unrelated to the actual context dossier.

The demo reads no imported personal/financial rows. Its deterministic code-owned
fixtures are not staged/published database imports and do not claim actual
publication approvals. Missing holder references block a matching hypothesis,
not a newly invented import requirement. Preview failure hides cached candidates.
Actual source fields remain blocked; existing authorized import review APIs
continue to work. No write/approve/apply mapping workflow exists.

## Files in this increment

- `backend/clients/source_mapping.py`: object/financial scope, shared admission
  fences, fresh IAM checks, bounded signed peer call and strict synthetic response
  validation. Client does not receive imports.* grants; Integration checks them.
- `backend/integration_service/mapping_examples.py`: versioned pure synthetic
  examples; no database/filesystem/network query and no shared mutable results.
- `backend/integration_service/source_mapping.py`: existing client_crm caller
  authentication, fresh Integration-owned IAM import/finance decisions;
  explicit published-mode denial.
- `backend/integration_service/private.py`: private route registration;
  `backend/config/urls.py`: additive public GET;
  `backend/contracts/additions.py`: reviewed additive route only. Original
  frozen baseline and existing OpenAPI operations are not edited.
- `backend/clients/tests_source_mapping.py` and
  `backend/integration_store/tests_source_mapping.py`: synthetic case, denial,
  invalid-peer, permission, no-mutation and determinism checks.
- `frontend/src/features/clients/SourceMappingPreview.tsx` and
  `ClientWorkspace.tsx`: opt-in French preview, explanations, source IDs,
  provenance, scenario choice, validation and fail-closed display.
- `frontend/e2e/source-mapping.spec.ts`: three real browser workflows covering
  all six cases, ordinary-reader denial, no real-mode query, mobile layout,
  reload and unavailable-source recovery.
- `infra/acceptance/source_mapping.py`: six live Gateway/TLS/IAM/SQL check groups;
  temporary synthetic test role removed in finally.
- `scripts/compose_source_mapping_recovery.py`: actual IAM/Client/Integration
  outages and Integration/Client/PostgreSQL process restarts.
- Matrix, contract, this report, source mapping index, gap analysis, backlog
  and open questions. Private aggregate-only key profile is excluded from Git;
  no source values are exported or committed.

No model, migration, DB role/schema/ownership, Compose, gateway, key/audience,
service extraction or Carthago change. Successful preview reads create no
business journal/outbox entries; existing denied-access auditing and nonce
replay persistence remain unchanged. No relationship is stored anywhere.

## Verification commands

```powershell
docker compose -f compose.yaml -f compose.test.yaml up --build -d
docker compose -f compose.yaml -f compose.test.yaml restart gateway
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/source_mapping.py
python scripts/compose_source_mapping_recovery.py --test
$env:AICED_E2E_SCALE='1'
python scripts/compose_browser.py --test
Remove-Item Env:AICED_E2E_SCALE
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/import_dashboard.py
python scripts/compose_import_dashboard_restart.py --test
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
python scripts/compose_inventory.py --test
```

All database probes use the existing disposable test volume and synthetic marker.
Run role/outage/browser suites sequentially. Do not delete volumes. Main stack
startup remains `docker compose up --build -d`; the separate test overlay is
unchanged. Docker availability, executed results and limitations follow below.

## Required next business decisions

Approve source namespaces/key positions; holder vs AH relationships, optional
and joint-holder cardinalities; explicit evidence for source-to-AICED UUID
links; read-only per-field authority and correction workflow; financial and
compliance field allowlists; source object visibility/reassignment/revocation;
version/as-of selection, duplicate conflicts and retention. See named pending
decision IDs in the matrix. No signed-off policy is invented.

After approval, define and test a narrowly scoped read-only source projection
with a reviewed link registry contract, bounded snapshot reads and fresh
Client-owned object authorization. Registry ownership/schema remains undecided;
no infrastructure or ownership migration is authorized by this preparation.
Financial KPIs, identity/account writes and managerial/team visibility are
outside this delivery. Local Docker verification is not production readiness.

## Executed verification results

- Docker Engine **29.9.3** reachable; actual compiled TypeScript/Vite container
  build passed. Eight existing Compose configurations validate with distinct
  main/test credentials and volumes; no Compose file was edited.
- Final backend regression after the authorization-boundary correction:
  **189 general + 5 IAM + 13 Integration + 18 Commercial = 225 passed**.
- Initial targeted browser run: two failures/one pass because the first Client
  implementation incorrectly required imports.view in its deliberately filtered
  IAM grant snapshot. Correction: Client retains dossier/financial authorization;
  Integration checks its own import grant. IAM snapshot contract/keys/prefixes
  are unchanged. The corrected three targeted browser tests all passed.
- **6 live source-mapping integration groups passed**: all six candidate cases;
  no business table/journal/outbox changes on successful reads; hidden dossier
  and IT denial; valid signed synthetic request, forged/replayed request
  rejection, signed published-mode denial; exclusive IAM/Client fence denial;
  existing-session role and import-only revocation/recovery; immutable published
  synthetic snapshot UPDATE denied by Integration runtime credentials.
- **6 actual outage/restart checks passed**: Integration/Client/IAM unavailable
  gives no candidates/fallback and recovers identical payloads with the same
  session; Integration/Client/PostgreSQL process restart preserves identical
  six-scenario fixture/provenance responses. This demonstrates deterministic
  fixture availability after restart, not persistence of mapping relationships:
  none are ever stored.
- **15 existing live security/integration groups passed**: restricted schema
  credentials, four migration histories, CSRF, authorization reassignment and
  revocation ordering, internal signatures/replay, transactional audit/outbox
  rollback and signed delivery deduplication.
- **51 public routes / 64 method-path checks passed**, with OpenAPI compatibility.
  The one additive public GET is explicitly reviewed; historical baseline intact.
- Actual test inventory passed seven healthy containers, four distinct Django
  processes, internal DNS, restricted credentials and gateway-only public port.
- Mobile synthetic preview screenshot inspected privately; no page overflow,
  candidate table scrolls within its container, provenance is available in details.
- Final full Chromium regression: **38 passed, 1 failed, 1 intentionally skipped**
  (40 tests). All three new mapping tests passed, as did the 10,000-opportunity
  scale test and the three-template import/publication flow. The failed existing
  `pipeline.spec.ts` create/status/concurrency/pagination test received HTTP 503
  on a search while expecting nine opportunities. It occurred on two full-suite
  runs; old counts were hidden safely. Commercial logs confirm 503, but this
  increment does not establish its precise underlying timing/transport cause.
  No pipeline implementation, timeout, authorization, test assertion or retry
  policy was changed to force a pass. The isolated unchanged pipeline test then
  **passed** (26.3 seconds); that does NOT turn the full-suite result green.
  Reports/logs are preserved privately as `source-mapping-full-browser.json`,
  `source-mapping-full-browser.log`, `source-mapping-initial-full-browser.*`
  and `source-mapping-isolated-pipeline.log`.
- Real persisted snapshot check passed again on the final browser-created
  physical/legal/account fixtures: exact cells/digests/dates, publication
  provenance, one journal/outbox pair, no matching identity/account creation;
  payloads and SQL fingerprints survived actual Integration and PostgreSQL
  restarts. This is distinct from the code-owned mapping examples.
- Main local stack rebuilt through unchanged Compose, gateway restarted after
  service recreation. A read-only smoke test on a labelled synthetic CRM client
  passed all six preview scenarios on `http://127.0.0.1:5187` without source
  upload or relationship activation. Final main and isolated-test inventories
  each show **seven healthy containers and four distinct Django services**.
  In the UI open an authorized client, Vue generale, then the synthetic mapping
  panel. Prospects do not display this panel and the API excludes them.

**Release limitation:** full application browser regression is not entirely
green because of the repeatable-in-suite, isolated-passing pipeline 503.
Investigate the existing S13 bounded/linear scan and overlapping navigation
requests under measured load before claiming general release readiness. Source
preparation end-to-end workflows passed, but no production readiness or complete
application regression success is claimed. Raising resource limits, bypassing
Client authorization or changing infrastructure is not a remedy in this increment.

Operational limits: fixture set only, at most ten records/relations per response
(currently two or three records); no arbitrary search, upload-derived matching,
bulk matching, current-version selection, link persistence, confirmed identity,
real published-snapshot field access or new financial computation. One bounded
Integration request per preview; existing IAM checks are uncached. Versioned
examples survive restart because they are code fixtures. Existing source
snapshot persistence is verified separately through the real import workflow.
