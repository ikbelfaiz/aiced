# Publication configuration proposals - NOT APPROVED / NOT ACTIVE

These proposals create no database rules and authorize no publication or CRM mapping.
Basis: `data-import-workflow-review.md`, positional schema v1 and `import-source-mapping.md`.

| Source | Candidate configuration requiring AMEN INVEST decision | Required evidence / approval |
| --- | --- | --- |
| Tier Personnes Physiques | Schema v1; candidate columns B (2) versus AC (29); ISO or DMY explicitly chosen, operational usage | Approve the source key and its meaning, uniqueness scope, missing/duplicate handling, date format and independent publication reviewers. Neither candidate is a confirmed client identity. |
| Compte titre | Schema v1; candidate column E (5); ISO or DMY explicitly chosen, operational usage | Approve account identifier semantics, uniqueness, required fields, dates, visibility and publication policy. Holder references are not approved client relationships. |

AMEN INVEST must name the approving business owner, decision reference, effective configuration and authorized reviewers. A rule proposer records the approved policy rationale; a different authorized reviewer approves that version. Each upload still requires independent publication review. No automatic contact, identity merge, account creation or Client 360 projection is authorized.

Existing legacy rules mentioning tests are historical evidence, not operational approval. Do not relabel them. Synthetic rules are only for verified synthetic fixtures in the isolated test environment. Declaring a file synthetic does not establish that its contents are fictional.

Operational source-record visibility, retention, relationship ownership and source-to-client mappings remain separate approval gates even after publication configuration approval.
