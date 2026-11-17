"""Versioned, deterministic SYNTHETIC examples; never queries an import or CRM table."""
import hashlib
import json

SCENARIOS = ('unique', 'ambiguous', 'missing', 'duplicate', 'multiple_accounts', 'conflicting_identifiers')


def preview(scenario):
    if scenario not in SCENARIOS:
        raise ValueError('Unknown synthetic scenario')
    people = [{'ref': 'SYNTH-ROW-P1', 'template': 'physical', 'source_id': 'SYNTH-TIER-01',
               'alternate_id': 'SYNTH-ALT-01', 'fixture_client': 'SYNTH-CRM-P1'}]
    accounts = [{'ref': 'SYNTH-ROW-A1', 'account_id': 'SYNTH-ACCOUNT-01',
                 'holder_D': 'SYNTH-TIER-01', 'identifier_AH': None}]
    if scenario == 'ambiguous':
        # Same text across two source namespaces is not a confirmed identity.
        people.append({'ref': 'SYNTH-ROW-L1', 'template': 'legal', 'source_id': 'SYNTH-TIER-01',
                       'alternate_id': None, 'fixture_client': 'SYNTH-CRM-L1'})
    if scenario == 'missing':
        people[0]['source_id'] = None
        accounts[0]['holder_D'] = None
    if scenario == 'duplicate':
        accounts.append({**accounts[0], 'ref': 'SYNTH-ROW-A2'})
    if scenario == 'multiple_accounts':
        accounts.append({**accounts[0], 'ref': 'SYNTH-ROW-A2', 'account_id': 'SYNTH-ACCOUNT-02'})
    if scenario == 'conflicting_identifiers':
        people.append({'ref': 'SYNTH-ROW-L1', 'template': 'legal', 'source_id': 'SYNTH-TIER-02',
                       'alternate_id': None, 'fixture_client': 'SYNTH-CRM-L1'})
        accounts[0]['identifier_AH'] = 'SYNTH-TIER-02'
    relations = []
    for account in accounts:
        holder = account['holder_D']
        matches = [p for p in people if holder and p['source_id'] == holder]
        status = 'candidate_unique'
        if not holder or not matches:
            status = 'missing_identifier'
        elif account['identifier_AH'] and account['identifier_AH'] != holder:
            status = 'conflicting_identifiers'
        elif sum(a['account_id'] == account['account_id'] for a in accounts) > 1:
            status = 'duplicate_identifier'
        elif len(matches) > 1:
            status = 'ambiguous_candidate'
        relations.append({'account_ref': account['ref'], 'status': status,
                          'person_candidates': [p['ref'] for p in matches],
                          'fixture_client_candidates': [p['fixture_client'] for p in matches],
                          'confirmed': False})
    raw = {'people': people, 'accounts': accounts}
    digest = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
    records = []
    for index, row in enumerate(people + accounts, 2):
        template = row.get('template', 'accounts')
        records.append({**row, 'template': template,
                        'validation_status': 'synthetic_mapping_blocked' if scenario in ('missing', 'duplicate') else 'synthetic_technical_only',
                        'provenance': {'dataset': 'SYNTH-MAPPING-v1', 'batch_reference': 'SYNTH-BATCH-' + template,
                                       'row_number': index, 'source_as_of': '2024-06-01', 'digest': digest,
                                       'publication_state': 'illustrative_fixture_not_a_published_import'}})
    return {'mode': 'synthetic', 'scenario': scenario, 'dataset_version': 'SYNTH-MAPPING-v1',
            'real_source_access': False, 'mapping_approved': False, 'relationships_persisted': False,
            'hypothesis': 'Unapproved demo: account D equals person B; AH is a separate, unresolved identifier.',
            'records': records, 'relationships': relations}

