# S16 source preparation: ownership and internal read contract

This is the source-preparation S16 requested after the import/dashboard increment.
The historical S16 commercial reporting document remains unchanged.

## Implemented synthetic contract

Browser: `GET /api/clients/{party_id}/source-mapping-preview/?scenario=unique`.
Other scenarios: `ambiguous`, `missing`, `duplicate`, `multiple_accounts`,
`conflicting_identifiers`. Unknown/repeated/extra parameters are rejected.
GET/OPTIONS only; there is no mapping save/approve/apply or real-data switch.

Client authorizes the actual context dossier before any peer call or result:
existing `clients.view` object scope, intersected with organization-scope
`clients.view_financial`, non-prospect. Integration then checks the existing
organization-scope `imports.view` and financial review grants. Client IAM
snapshots deliberately omit `imports.*`; that contract is not broadened.
This conservatively reuses the import review prerequisites for
fictional examples; it does NOT approve source visibility for real CRM users.
Ordinary readers, IT and import reviewers without Client access are denied.
The synthetic `SYNTH-CRM-*` references are NOT the current AICED dossier UUID.

Client sends a signed POST to Integration:
`/internal/v1/source-mapping/preview`.

```json
{
  "credentials": {"session_key":"<delegated>","method":"GET","host":"<gateway>","scheme":"http"},
  "actor_id":"<verified-actor-uuid>",
  "organization_id":"<Client-authorized-org-uuid>",
  "party_id":"<Client-authorized-context-uuid>",
  "mode":"synthetic",
  "scenario":"multiple_accounts"
}
```

Existing `Credentials` validation also accepts bounded CSRF/origin/referer fields.
No credentials are returned, stored in the fixture, logged or cached.
Only authenticated `client_crm` service callers are admitted. Existing pairwise
Client-to-Integration key, TLS/DNS, audience, timestamp, nonce and replay store
are reused unchanged. No new ingress/key/network/container is added. The shared
transport currently has an `INTEGRATION_AUDIT_*` configuration name; reuse does
not grant audit permissions or broaden accepted services.

Integration checks fresh IAM organization-level import/financial permissions
and verifies delegated actor identity. It returns only versioned code-owned
synthetic records, bounded to ten records and ten candidate relationships.
There are no snapshot-table, Client-table or source-file queries in the fixture
generator. Records contain source-key examples, provenance, validation status,
candidate references and `confirmed:false`. Every relation remains unapproved.

Response invariants:

- `mode:synthetic`, `dataset_version:SYNTH-MAPPING-v1`;
- `real_source_access:false`, `mapping_approved:false`,
  `relationships_persisted:false`;
- source/key/account/client references use the `SYNTH-` namespace;
- provenance explicitly says `illustrative_fixture_not_a_published_import`;
- no personal names, financial values, real source keys or confirmed links.

Client validates actor/org/context/scenario and these invariants, bounds and
explicit allowed fields before returning a restricted response. Unexpected
source fields or real identifiers fail closed. Frontend independently validates
the shape and hides cached candidates on source or permission errors.

Client admits the read behind existing shared IAM and Client visibility fences,
uses READ COMMITTED after admission, refreshes IAM grants before and after the
peer call, and rechecks the object. Failed fences, identity/grant changes,
expired sessions, unavailable peers or processing budget exhaustion return no
candidates. Processing checks use a four-second budget, per-peer timeout <=3s,
SQL statement timeout 3.5s; the existing internal 64KiB request/response cap
also applies. No retries, background scan or business-data cache is introduced.

`mode:published` is explicitly recognized and always rejected with 403:
mapping and source-object visibility are not approved. No runtime setting,
uploaded policy rationale or caller-supplied ID bypasses that block. Existing
authorized import review/batch preview remains unchanged; it is not a Client
360 source-data grant.

## Future published-snapshot contract: proposed, NOT activated

An approved read contract should accept at most 50 explicit snapshot UUIDs per
request, a Client-owned dossier UUID, immutable approved mapping and visibility
policy versions, delegated credentials and a fresh Client scope revision.
No arbitrary field names, source-table queries, fuzzy search or unbounded export.
Proposed AICED-private operation: `POST /internal/v1/source-snapshots/read-authorized`.
This operation is documented only and has NO registered runtime route.

Required sequence after business approval:

1. Client resolves the live IAM actor and authorizes the dossier/financial action
   before asking for records. Any scope assertion is produced by Client code,
   never accepted from browser parameters. Client retains its visibility fence
   during the bounded read and verifies scope again before returning it.
2. Integration verifies caller, fresh IAM identity and applicable approved source
   visibility policy. It verifies the approved link for this exact dossier,
   organization, source namespace and requested snapshots. A bare Client UUID,
   organization-wide import grant or source identifier is insufficient.
3. Integration reads only its own published immutable snapshots, excludes staged
   rows, applies the approved field allowlist before counts/selection, and
   returns provenance: snapshot/row/batch IDs, digest, template/version,
   key position, policy version, source-as-of, publication time and reviewer.
4. Missing/revoked policy, unknown/ambiguous link, wrong organization, staged
   record, revoked dossier access, unavailable IAM/Client decision or any
   incomplete authorization yields a denial/unavailable response without raw
   cells, counts, existence hints or a cached fallback.

Link-registry ownership/schema, persistence/review workflow, grant matrix,
policy versioning/revocation, as-of selection and joint-account representation
must first be approved. They are NOT implemented or assigned to a new owner in
this increment. Client-to-Integration signed scope assertions and revocation
tests must be reviewed against that eventual registry contract; documented
future fields are not currently trusted as an authorization mechanism.

## Ownership and approvals

IAM owns identity, live sessions and grants. Client & CRM owns dossier visibility,
CRM business objects and editable profiles. Integration owns snapshots,
provenance, publication history and source-side field/policy enforcement.
Carthago remains authoritative and strictly read-only; no credentials,
connector, endpoint or financial semantics are invented.

See [the field-level approval matrix](source-mapping-approval-matrix.md).
No source-to-Client link, ExternalIdentity, Party or FinancialAccount mutation
is made. No database model, migration, ownership boundary or Compose change.
