"""Actual Docker HTTP/SQL evidence, using browser-created synthetic fixtures only."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import psycopg

sys.path[:0] = ['/app', '/scripts']
from s3_rehearsal import Browser

cfg = json.loads(Path('/private/config.json').read_text())
admin = cfg['admin']
assert admin['POSTGRES_HOST'] == 'db' and admin['POSTGRES_DB'] == 'aiced_s7_disposable'
url = 'http://gateway:8080'
password = admin['AICED_SEED_PASSWORD']


def principal(role):
    browser = Browser(url)
    browser.login('synthetic.' + role + '.a', password)
    return browser


operator, reviewer, other = principal('operator'), principal('reviewer'), principal('operator')
status, context, _ = operator.request('/api/imports/context/')
assert status == 200
org = next(item['id'] for item in context['organizations'] if item['upload'])
root = f'/api/imports/{org}/'
manifest = json.loads(Path('/private/import-dashboard-manifest.json').read_text())
legal = next(item for item in manifest if item['template'] == 'legal')
policy_id = legal['policy_id']
checks = []

with psycopg.connect(host='db', dbname=admin['POSTGRES_DB'], user=admin['POSTGRES_USER'], password=admin['POSTGRES_PASSWORD'], autocommit=True) as c:
    assert c.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()[0] == 'aiced-s7-synthetic-only'
    assert c.execute("SELECT count(*) FROM aiced_integration.ingestion_importpolicy WHERE approved_at IS NOT NULL AND revoked_at IS NULL AND data_scope!='legacy' GROUP BY organization_id,template,template_version,date_format,data_scope HAVING count(*)>1").fetchall() == []
    config = dict(template='legal', key_column=2, template_version=1, data_scope='synthetic', date_format='ISO', rationale='SYNTHETIC REVIEW legal: snapshots only, no CRM mapping approved.')
    before = c.execute('SELECT count(*) FROM aiced_integration.ingestion_importpolicy').fetchone()[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda b: b.request(root+'policies/', config), [operator, other]))
    assert all(status == 201 and data['id'] == policy_id for status, data, _ in results)
    assert c.execute('SELECT count(*) FROM aiced_integration.ingestion_importpolicy').fetchone()[0] == before
    checks.append('Concurrent identical proposals return the existing approval without duplicate rows')
    # Two independently reviewed proposals cannot become active simultaneously.
    # Use synthetic-only accounts/DMY, which the browser does not approve.
    assert c.execute("SELECT count(*) FROM aiced_integration.ingestion_importpolicy WHERE organization_id=%s AND template='accounts' AND date_format='DMY' AND data_scope='synthetic' AND approved_at IS NOT NULL AND revoked_at IS NULL", [org]).fetchone()[0] == 0
    proposed = []
    for suffix in ['A', 'B']:
        status, data, _ = operator.request(root+'policies/', dict(template='accounts', key_column=5, date_format='DMY', data_scope='synthetic', rationale='SYNTHETIC concurrency policy '+suffix+'; no real source authorization.'))
        assert status == 201
        proposed.append(data['id'])
    reviewer2 = principal('reviewer')
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            approvals = list(pool.map(lambda pair: pair[0].request(root+f'policies/{pair[1]}/approve/', {}), zip([reviewer, reviewer2], proposed)))
        assert sorted(result[0] for result in approvals) == [200, 400], approvals
        assert c.execute("SELECT count(*) FROM aiced_integration.ingestion_importpolicy WHERE id=ANY(%s::uuid[]) AND approved_at IS NOT NULL AND revoked_at IS NULL", [proposed]).fetchone()[0] == 1
    finally:
        for ident in proposed:
            assert reviewer.request(root+f'policies/{ident}/revoke/', {})[0] == 200
    checks.append('Concurrent independent approvals permit exactly one active configuration; explicit revocation retains both histories')
    status, preview, _ = reviewer.request(root+f"batches/{legal['batch_id']}/")
    assert status == 200 and preview['policy_match']['policy']['id'] == policy_id
    assert preview['batch']['data_scope'] == 'synthetic'
    assert c.execute('SELECT count(*) FROM aiced_integration.ingestion_importbatch WHERE policy_id=%s AND status=%s', [policy_id, 'published']).fetchone()[0] >= 2
    checks.append('At least two separately reviewed uploads reuse one approved rule; server suggestion matches historical provenance')
    assert operator.request(root+f"batches/{legal['batch_id']}/publish/", {'policy_id':policy_id})[0] == 403
    denied = principal('it')
    assert denied.request(root+'policies/')[0] == 403
    assert denied.request(root+f"batches/{legal['batch_id']}/")[0] == 403
    checks.append('Uploader cannot self-publish even on replay; IT cannot read rules or suggestions')
    # Probe the immutable version with restricted service credentials. Roll back
    # each denied statement; do not disable triggers, fences or protections.
    env = cfg['integration']
    with psycopg.connect(host='db', dbname=env['POSTGRES_DB'], user=env['POSTGRES_USER'], password=env['POSTGRES_PASSWORD'], options='-c search_path=aiced_integration,public', autocommit=True) as runtime:
        for statement in ['UPDATE ingestion_importpolicy SET rationale=\'forbidden\' WHERE id=%s', 'DELETE FROM ingestion_importpolicy WHERE id=%s']:
            try:
                runtime.execute(statement, [policy_id])
            except psycopg.Error:
                pass
            else:
                raise AssertionError('Mutable publication history')
    checks.append('Restricted Integration role cannot rewrite or delete publication history')
    inconsistent = c.execute("SELECT count(*) FROM aiced_integration.integration_store_journal j LEFT JOIN aiced_integration.integration_store_outbox o ON o.event_id=j.id WHERE j.action IN ('imports.published','imports.policy_created','imports.policy_approved','imports.policy_reused') AND o.event_id IS NULL").fetchone()[0]
    assert inconsistent == 0
    checks.append('Publication, proposal, approval and reuse journals retain corresponding transactional outbox events')

Path('/private/publication-rules-report.json').write_text(json.dumps({'status':'passed','checks':checks}, indent=2))
print('PASS:', len(checks), 'publication rule HTTP/SQL integration checks')
