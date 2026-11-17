# Source workbook mapping proposal and import/report investigation

Follow-up preparation: [field-level approval matrix](source-mapping-approval-matrix.md),
[synthetic/internal contract](source-mapping-contract.md) and
[Docker validation](source-mapping-preparation-validation.md). The current
synthetic preview does not activate any mapping proposed in this document.

Inspected 2026-11-16. Reference workbooks were inspected locally for headers/types only; no customer rows were imported or copied into this document. Synthetic fixtures alone are used for validation.

## Current workflow and root cause

Upload -> bounded XLSX parsing -> immutable positional StagingRow JSON cells, validation errors/warnings and normalized dates -> explicit separate-user review -> immutable SourceSnapshot pointing to accepted rows. ImportBatch preserves digest, source date, template version, uploader, publisher, publication time and policy. Original XLSX bytes are parsed and hashed, not archived as a downloadable file. Data lives in PostgreSQL schema aiced_integration, persisted in the Compose database volume.

Staging is a saved, deliberate review state, not a failed persistence operation. A policy must select the source key and date format, have a rationale, and be approved by a user other than its creator. A batch must then be explicitly published by a user other than its uploader with imports.approve and the existing organization-level financial/import grants. Rejected rows require explicit exclusion. No valid rows, missing/revoked/mismatched policy, missing rights or unavailable authorization prevent publication. Synthetic policy approval demonstrates the mechanism, not AMEN INVEST approval for production data.

Publication already exists in the UI (Gestion des donnees -> Examiner -> Examiner la publication), and all source rows including rejected rows remain inspectable. The current change adds explicit blocker explanations and visible publication provenance. Published rows remain accessible through the existing authorized batch preview API; this is source inspection, not Client 360 authorization.

No Client or reporting consumer maps SourceSnapshot into Party, ExternalIdentity or FinancialAccount. That missing business connection is intentional pending identity, field ownership and object-visibility policies. Neither publication nor a complete export creates, merges, overwrites or deletes clients/accounts.

## Complete positional inventory

Every listed column is currently supported as a preserved source cell, not an approved CRM mapping. Position is authoritative: duplicate labels and trailing spaces are significant. Empty column A is preserved too. Observed types describe the reference files only, not an approved semantic type system.

### Tier Personnes Physiques.xlsx

Sheet: Tier; candidate key positions: [2, 29]. All fields -> StagingRow.cells[position]; source dates additionally -> normalized_dates[position].

| Position | Exact header | Observed Python types |
|---|---|---|
| 1 | (blank) | NoneType |
| 2 | `Identifiant` | str |
| 3 | `Nom` | NoneType |
| 4 | `Prénom` | NoneType |
| 5 | `Nom Complet` | NoneType |
| 6 | `Creation Date` | NoneType |
| 7 | `Type de pièce d'identité` | str |
| 8 | `N° de pièce d'identité` | str |
| 9 | `Date de naissance` | str |
| 10 | `Commentaire` | str |
| 11 | `Chargé client` | str |
| 12 | `Téléphone` | str |
| 13 | `Mobile` | str |
| 14 | `Fax` | str |
| 15 | `Email` | NoneType |
| 16 | `Fonction Contact` | str |
| 17 | `Secteur d'activité` | str |
| 18 | `Adresse` | str |
| 19 | `Ville` | str |
| 20 | `Code postal` | str |
| 21 | `Risque LAB/FT` | str |
| 22 | `Sexe` | str |
| 23 | `Civilité` | str |
| 24 | `Etat Civil` | str |
| 25 | `Père` | str |
| 26 | `mère` | str |
| 27 | `Code SWIFT` | str |
| 28 | `Biccode` | str |
| 29 | `Identifiant` | str |
| 30 | `Pays de nationalité` | str |
| 31 | `Résident` | str |
| 32 | `Pays de résidence` | str |
| 33 | `Pays de naissance` | str |

### Tier Personnes Morales.xlsx

Sheet: Tier; candidate key positions: [2]. All fields -> StagingRow.cells[position]; source dates additionally -> normalized_dates[position].

| Position | Exact header | Observed Python types |
|---|---|---|
| 1 | (blank) | NoneType |
| 2 | `Identifiant` | str |
| 3 | `Libellé Court` | NoneType |
| 4 | `Libellé Long / Raison Sociale` | NoneType |
| 5 | `Creation Date` | NoneType |
| 6 | `Chargé client` | str |
| 7 | `Téléphone` | str |
| 8 | `Mobile` | str |
| 9 | `Fax` | str |
| 10 | `Fonction Contact` | str |
| 11 | `Secteur d'activité` | str |
| 12 | `Adresse` | str |
| 13 | `Ville` | str |
| 14 | `Code postal` | str |
| 15 | `Sexe` | str |
| 16 | `Civilité` | str |
| 17 | `Etat Civil` | str |
| 18 | `Code SWIFT` | str |
| 19 | `Risque LAB/FT` | str |
| 20 | `Biccode` | str |
| 21 | `Pays de nationalité` | str |
| 22 | `Résident` | str |
| 23 | `Pays de résidence` | str |
| 24 | `Pays de naissance` | str |
| 25 | `Commentaire` | str |

### Compte titre.xlsx

Sheet: Compte titre; candidate key positions: [5]. All fields -> StagingRow.cells[position]; source dates additionally -> normalized_dates[position].

| Position | Exact header | Observed Python types |
|---|---|---|
| 1 | (blank) | NoneType |
| 2 | `Agence UIB` | str |
| 3 | `Fréquence du reporting` | str |
| 4 | `Détenteur du compte` | str |
| 5 | `Numéro de compte ` | str |
| 6 | `Prénom` | NoneType |
| 7 | `Nom` | NoneType |
| 8 | `Nom Complet` | NoneType |
| 9 | `Date d'ouverture` | str |
| 10 | `CEA` | str |
| 11 | `Pack de frais` | str |
| 12 | `Creation Date` | str |
| 13 | `Update Date` | str |
| 14 | `Update User` | str |
| 15 | `Type de pièce d'identité` | str |
| 16 | `Date de naissance` | str |
| 17 | `Chargé client` | str |
| 18 | `Status` | str |
| 19 | `Téléphone` | str |
| 20 | `Mobile` | str |
| 21 | `Fax` | str |
| 22 | `Email` | str |
| 23 | `Fonction Contact` | str |
| 24 | `Secteur d'activité` | str |
| 25 | `Adresse` | str |
| 26 | `Ville` | str |
| 27 | `Code postal` | str |
| 28 | `Risque LAB/FT` | str |
| 29 | `Sexe` | str |
| 30 | `Civilité` | str |
| 31 | `Etat Civil` | str |
| 32 | `Swiftcode` | str |
| 33 | `Biccode` | str |
| 34 | `Identifiant` | str |
| 35 | `Type de gestion` | str |
| 36 | `Catégorie d'avoirs` | str |
| 37 | `Pays de nationalité` | str |
| 38 | `Resident` | str |
| 39 | `Pays de résidence` | str |
| 40 | `Foreign` | str |
| 41 | `Pays de naissance` | str |

## Supported validation and proposed semantic mappings

| Fields | Current supported use | Proposed downstream use / decision required |
|---|---|---|
| Physical B/AC, legal B | Text candidate keys; approved policy chooses a position | Establish stable source identifier, uniqueness, history and source namespace; neither equals the AICED UUID by default |
| Account E | Text source account key | Confirm account identifier semantics, institution and uniqueness before FinancialAccount mapping |
| Account D and AH | Preserved raw values only | Holder/identifier relationship to physical B/AC or legal B is unknown; never join by name or assume interchangeability |
| Names / company labels | Raw source text | Possible display labels after authority and reconciliation rules; no fuzzy identity merge |
| Phone/mobile/email/address | Raw source text | Source vs editable CRM authority, precedence, consent and correction workflow require approval |
| Fonction Contact / Secteur activite | Raw text without taxonomy | Fonction Contact is not assumed to be profession; sector normalization and CRM ownership require approval |
| Charge client | Raw source text | No automatic mapping to IAM actors, owners or object access |
| Birth/opening/creation/update dates | Explicit ISO/DMY or native Excel dates, separate ISO normalization | Confirm date meaning and source timestamp timezone before operational/financial metrics |
| Risque LAB/FT | Raw source text | Compliance classification; NOT investment risk, scoring or disengagement risk |
| CEA / Status / Type gestion / Categorie avoirs | Raw source text | Approved dictionaries and financial permissions required; no free/managed, active or investment-segment inference |
| Nationality/residence/identity document and other descriptive fields | Raw cells only | Data classification, retention, field authority and permitted users required |
| Balances/assets/valuation/currency/price/quantity/revenue | Absent usable source fields | No assets under management or performance calculation supported |

Technical validation: exact headers/order/sheet, no implicit numeric identifier conversion (leading zero protection), candidate text keys <=160 without edge whitespace, all duplicate occurrences rejected, dates valid/not after source date, dates of birth not future, date format explicit. Non-key business fields are not made mandatory without approval. Primitive strings/numbers/booleans/null are preserved; native dates serialized separately. Formulas/errors, dangerous ZIP/OOXML, macros/external links, oversized archives/rows/cells are rejected. See docs/import-templates.md and backend/ingestion/parser.py for exact resource caps.

A previously published key produces a warning and a reviewed new immutable source version, not an overwrite. Binary replay returns the same batch. Conflicting source identifiers require human review; no identity resolution is performed.

## Dashboard data sources and limits

| Indicator | Definition/source | Time / visibility |
|---|---|---|
| Accessible clients | Existing GET /api/clients/?page_size=1 count, prospects excluded | Current records, all dates; existing object scope before count |
| Opportunities by status | Existing GET /api/opportunities/?page_size=1 count + open/won/lost | Current statuses, all dates; Client-owned authorization before visible counts; bounded fail-closed pipeline |
| Recorded interactions | GET /api/clients/activity-report/ total, by_kind, daily | occurred_at within selected inclusive civil dates, explicit business timezone, authorized client/prospect scope |
| Personal appointments | Same report, starts_at in period | Owner-only existing agenda permissions; planned, not proof of realized contact |
| Prospect followups | Same report, next_action_date overdue/today/upcoming/unscheduled | Current business date, all existing prospect statuses; independent of report period/type |
| Campaign drafts | GET /api/campaigns/?page_size=1 count | Current private drafts, all dates; no active/sent/targeted campaign inference |
| Encours / retention / approved segmentation | Unavailable with explicit reasons | Missing source facts or approved definition; no invented formula |

The previous home page connected only the client count. It still claimed the Commercial module and interactions were unavailable after S11/S16. The home page now composes the existing S16 report and shows the live client count. Financial cards retain explicit unavailable reasons. Illustrative numbers remain development-preview-only and absent in compiled production mode. There is no separate snapshot financial KPI API, because no approved source-to-client object visibility mapping exists. Import organization scope must never be reused as permission to expose source clients to ordinary CRM users.

Default report period: last 30 civil days including today; adjustable 1-93 days, configurable Africa/Tunis default. Period/type apply only to interactions and personal appointments. Current stock metrics are separately labelled. Existing service APIs apply authorization before aggregation. Source failures hide previous counts for that source; independent sources may remain available. These are independent reads, not a distributed snapshot. No financial or managerial KPI completion claimed.

## Required AMEN INVEST decisions

Approve source keys (especially physical B vs AC), holder/account/party relationships and conflict handling; authoritative per-field ownership and corrections; allowed source record users/object linkage; source dictionaries and date/timestamp meaning; retention/encryption/backups; financial facts and KPI definitions. Source read-only consultation in Client 360 stays blocked until approved object mapping and access policy exist. No new infrastructure or direct cross-schema reads are introduced.

## Verification

See docs/import-dashboard-validation.md for actual commands, results and remaining limits.
