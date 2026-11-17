# S16 - Source mapping preparation: approval matrix

This S16 designation follows the current user request. The earlier S16 Commercial Activity Reporting record is preserved separately; no historical milestone evidence is renamed.

Status: PREPARATION ONLY. No source-to-client relationship or real Client 360 source field is approved or activated. This matrix proposes review decisions; it does not authorize writes to Carthago, Party, ExternalIdentity or FinancialAccount.

## Confirmed technical facts vs unapproved relationships

- Confirmed: positional workbook headers/types and current snapshot storage/publication contracts, listed in import-source-mapping.md. Existing internal AICED UUIDs remain independent. ExternalIdentity currently has unique(source,external_id); FinancialAccount has unique(source,external_id) and one required Party FK. These existing structural constraints do not prove the source relationship fits them.
- Unapproved: physical B vs AC; legal B namespace; account E uniqueness scope; account D holder representation; AH meaning; cross-file links; relationship to an existing AICED UUID. A shared string or name never confirms a relationship.
- Proposed cardinalities for review: an AICED client may have zero/many source observations and zero/many accounts; a source identifier may have many historical snapshots. Whether a source party maps to exactly one client, and whether accounts may be joint/multi-holder, is unknown. Do not force joint holders into the existing one-Party projection without approval.
- Missing B with AC present is not silently repaired. Missing D/AH blocks that matching hypothesis, not necessarily technical import publication. All-missing candidate source keys fail current parser validation. Numeric/whitespace identifiers and within-file duplicates follow existing parser rules. Repeated published keys across batches are historical observations, not automatically duplicate identities or replacements.
- Identical identifiers across physical/legal namespaces may be ambiguous. D and AH pointing to different parties is a conflict. No first-match, fuzzy/name match, normalization, implicit person-kind switch, latest-batch selection or automatic link is proposed as an approved rule.

A private aggregate-only inspection of the supplied reference workbook keys is saved in .local/ui-review/source-mapping-profile.json (missing, numeric, whitespace, duplicate and overlap counts; no values). Overlap counts demonstrate equality only, never referential integrity. Existing schema inspection also finds absent names/labels in these reference exports; matching by display name is unsafe even before considering homonyms. Private aggregates are not committed. Synthetic examples exercise every ambiguity regardless of observed export counts.

## Approval-ready field-level matrix

For every row: Data Integration owns raw cells, provenance and immutable snapshots. Source business authority is Carthago/source-owner subject to AMEN INVEST confirmation. Default source access in Client 360 is DENY. Any listed target is a proposal for a separate read-only presentation, never a write to that attribute. CRM-owned email/phone/profession/sector/notes remain independently editable with existing authorization. Approval columns below remain PENDING, not approved by a technical publication policy.

| Template / position | Exact field | Tentative display/relationship target | Ownership / visibility / approval decision |
|---|---|---|---|
| physical / 1 | `(blank)` | Preserved positional blank column; no business meaning | No display or relationship proposal |
| physical / 2 | `Identifiant` | Candidate source party key, never AICED UUID | Approve namespace, key position, uniqueness and change/history policy; PENDING |
| physical / 3 | `Nom` | Separate source identity label; existing Party/subtype names are NOT overwritten | Source identity read-only; approve identity evidence, exact link and authorized fields; PENDING |
| physical / 4 | `Prénom` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 5 | `Nom Complet` | Separate source identity label; existing Party/subtype names are NOT overwritten | Source identity read-only; approve identity evidence, exact link and authorized fields; PENDING |
| physical / 6 | `Creation Date` | Source date plus normalized value; no inferred financial reporting date | Approve date semantics, timestamp timezone, as-of/version selection; PENDING |
| physical / 7 | `Type de pièce d'identité` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 8 | `N° de pièce d'identité` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 9 | `Date de naissance` | Source date plus normalized value; no inferred financial reporting date | Approve date semantics, timestamp timezone, as-of/version selection; PENDING |
| physical / 10 | `Commentaire` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| physical / 11 | `Chargé client` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 12 | `Téléphone` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 13 | `Mobile` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| physical / 14 | `Fax` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| physical / 15 | `Email` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| physical / 16 | `Fonction Contact` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| physical / 17 | `Secteur d'activité` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 18 | `Adresse` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| physical / 19 | `Ville` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| physical / 20 | `Code postal` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| physical / 21 | `Risque LAB/FT` | Restricted source compliance label; NOT investment risk or scoring | Compliance authority, dictionary and explicit field-level role matrix; PENDING |
| physical / 22 | `Sexe` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 23 | `Civilité` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 24 | `Etat Civil` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 25 | `Père` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 26 | `mère` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 27 | `Code SWIFT` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 28 | `Biccode` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 29 | `Identifiant` | Candidate source party key, never AICED UUID | Approve namespace, key position, uniqueness and change/history policy; PENDING |
| physical / 30 | `Pays de nationalité` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 31 | `Résident` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 32 | `Pays de résidence` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| physical / 33 | `Pays de naissance` | Sensitive source identity attribute, no merge key assumption | Minimization, identity authority, allowed roles, masking/retention; PENDING |
| legal / 1 | `(blank)` | Preserved positional blank column; no business meaning | No display or relationship proposal |
| legal / 2 | `Identifiant` | Candidate source party key, never AICED UUID | Approve namespace, key position, uniqueness and change/history policy; PENDING |
| legal / 3 | `Libellé Court` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| legal / 4 | `Libellé Long / Raison Sociale` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| legal / 5 | `Creation Date` | Source date plus normalized value; no inferred financial reporting date | Approve date semantics, timestamp timezone, as-of/version selection; PENDING |
| legal / 6 | `Chargé client` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| legal / 7 | `Téléphone` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| legal / 8 | `Mobile` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| legal / 9 | `Fax` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| legal / 10 | `Fonction Contact` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| legal / 11 | `Secteur d'activité` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| legal / 12 | `Adresse` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| legal / 13 | `Ville` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| legal / 14 | `Code postal` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| legal / 15 | `Sexe` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| legal / 16 | `Civilité` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| legal / 17 | `Etat Civil` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| legal / 18 | `Code SWIFT` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| legal / 19 | `Risque LAB/FT` | Restricted source compliance label; NOT investment risk or scoring | Compliance authority, dictionary and explicit field-level role matrix; PENDING |
| legal / 20 | `Biccode` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| legal / 21 | `Pays de nationalité` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| legal / 22 | `Résident` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| legal / 23 | `Pays de résidence` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| legal / 24 | `Pays de naissance` | Sensitive source identity attribute, no merge key assumption | Minimization, identity authority, allowed roles, masking/retention; PENDING |
| legal / 25 | `Commentaire` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| accounts / 1 | `(blank)` | Preserved positional blank column; no business meaning | No display or relationship proposal |
| accounts / 2 | `Agence UIB` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 3 | `Fréquence du reporting` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 4 | `Détenteur du compte` | Unresolved holder/party reference; candidate relationship only | Approve referenced namespace, equality semantics, missing/conflict/joint-holder cardinality; PENDING |
| accounts / 5 | `Numéro de compte ` | Candidate source key, never AICED UUID; account key | Approve namespace, key position, uniqueness and change/history policy; PENDING |
| accounts / 6 | `Prénom` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 7 | `Nom` | Separate source identity label; existing Party/subtype names are NOT overwritten | Source identity read-only; approve identity evidence, exact link and authorized fields; PENDING |
| accounts / 8 | `Nom Complet` | Separate source identity label; existing Party/subtype names are NOT overwritten | Source identity read-only; approve identity evidence, exact link and authorized fields; PENDING |
| accounts / 9 | `Date d'ouverture` | Source date plus normalized value; no inferred financial reporting date | Approve date semantics, timestamp timezone, as-of/version selection; PENDING |
| accounts / 10 | `CEA` | Read-only source account classification, no financial KPI | Finance/source authority, dictionary and field/object visibility; PENDING |
| accounts / 11 | `Pack de frais` | Read-only source account classification, no financial KPI | Finance/source authority, dictionary and field/object visibility; PENDING |
| accounts / 12 | `Creation Date` | Source date plus normalized value; no inferred financial reporting date | Approve date semantics, timestamp timezone, as-of/version selection; PENDING |
| accounts / 13 | `Update Date` | Source date plus normalized value; no inferred financial reporting date | Approve date semantics, timestamp timezone, as-of/version selection; PENDING |
| accounts / 14 | `Update User` | Source date plus normalized value; no inferred financial reporting date | Approve date semantics, timestamp timezone, as-of/version selection; PENDING |
| accounts / 15 | `Type de pièce d'identité` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 16 | `Date de naissance` | Source date plus normalized value; no inferred financial reporting date | Approve date semantics, timestamp timezone, as-of/version selection; PENDING |
| accounts / 17 | `Chargé client` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 18 | `Status` | Read-only source account classification, no financial KPI | Finance/source authority, dictionary and field/object visibility; PENDING |
| accounts / 19 | `Téléphone` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 20 | `Mobile` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| accounts / 21 | `Fax` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| accounts / 22 | `Email` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| accounts / 23 | `Fonction Contact` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| accounts / 24 | `Secteur d'activité` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 25 | `Adresse` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| accounts / 26 | `Ville` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| accounts / 27 | `Code postal` | Separate source contact/context; no CRMProfile overwrite or automatic profession mapping | Confirm per-field source vs CRM authority, correction flow and visibility; PENDING |
| accounts / 28 | `Risque LAB/FT` | Restricted source compliance label; NOT investment risk or scoring | Compliance authority, dictionary and explicit field-level role matrix; PENDING |
| accounts / 29 | `Sexe` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 30 | `Civilité` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 31 | `Etat Civil` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 32 | `Swiftcode` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 33 | `Biccode` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 34 | `Identifiant` | Unresolved holder/party reference; candidate relationship only | Approve referenced namespace, equality semantics, missing/conflict/joint-holder cardinality; PENDING |
| accounts / 35 | `Type de gestion` | Read-only source account classification, no financial KPI | Finance/source authority, dictionary and field/object visibility; PENDING |
| accounts / 36 | `Catégorie d'avoirs` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 37 | `Pays de nationalité` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 38 | `Resident` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 39 | `Pays de résidence` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 40 | `Foreign` | Source-only descriptive value; no current domain field | Source read-only; classify field and approve purpose/audience/retention; PENDING |
| accounts / 41 | `Pays de naissance` | Sensitive source identity attribute, no merge key assumption | Minimization, identity authority, allowed roles, masking/retention; PENDING |

## Decisions to sign off

| ID | Required decision | Proposed safe default | Approver / status |
|---|---|---|---|
| MAP-01 | Source namespaces, physical B/AC, legal B, account E and change rules | No source identity link | AMEN INVEST source owner / PENDING |
| MAP-02 | D/AH meaning, optionality, physical/legal disambiguation and joint holders | Candidate/conflict only | AMEN INVEST business + source owner / PENDING |
| MAP-03 | Evidence linking source party to an existing AICED UUID; correction/review/versioning | No automatic or manual persistence endpoint yet | AMEN INVEST CRM + source owner / PENDING |
| OWN-01 | Each field above: authority, source/CRM separation, correction and provenance | Display source separately, no overwrite | AMEN INVEST CRM/source/compliance / PENDING |
| VIS-01 | Client object capability, field allowlist, organization/assigned/team scopes, financial/compliance restrictions | Deny all real source fields | AMEN INVEST security/compliance/business / PENDING |
| VIS-02 | Joint account visibility, historical permissions, reassignment and revocation | No inherited holder-wide or organization-wide access | AMEN INVEST security/business / PENDING |
| LIFE-01 | Current/as-of version selection, duplicate/conflict treatment, retention/encryption/export/audit reads | Immutable history; no absence deletion | AMEN INVEST source/compliance / PENDING |

Sign-off must record named approver, decision/version, effective date, scope, approved fields, fixture acceptance and revocation procedure. No such approval is supplied or fabricated in this increment.

## Proposed next increment after approval

Implement a narrowly scoped, read-only source projection using a reviewed link registry contract and explicit field allowlist. Client owns every object decision; Integration owns snapshot selection/provenance and source visibility enforcement. Revalidate IAM/object/policy revisions before returning data, with bounded requests and no schema-crossing ORM access. Link persistence, account projection changes, financial indicators and external-system writes are separate approvals, not implied by this plan. See source-mapping-contract.md for disabled real-source protocol and current synthetic implementation.
