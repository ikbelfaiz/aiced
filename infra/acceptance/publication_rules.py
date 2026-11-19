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
checks = []

with psycopg.connect(host='db', dbname=admin['POSTGRES_DB'], user=admin['POSTGRES_USER'], password=admin['POSTGRES_PASSWORD'], autocommit=True) as c:
    assert c.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()[0] == 'aiced-s7-synthetic-only'
    before = c.execute('SELECT count(*) FROM aiced_integration.ingestion_importpolicy').fetchone()[0]
    config = dict(template='legal', key_column=2, data_scope='synthetic', date_format='ISO', rationale='SYNTHETIC')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda b: b.request(root+'policies/', config), [operator, other]))
    assert all(result[0] == 405 for result in results)
    assert c.execute('SELECT count(*) FROM aiced_integration.ingestion_importpolicy').fetchone()[0] == before
    checks.append('Concurrent public creation attempts rejected without policy mutations')
    for item in manifest:
        status, preview, _ = reviewer.request(root+f"batches/{item['batch_id']}/")
        assert status == 200 and preview['fixed_configuration']['key_column'] == (5 if item['template'] == 'accounts' else 2)
        assert preview['batch']['fixed_configuration_version'] == 1 and preview['batch']['policy_id'] is None
        assert operator.request(root+f"batches/{item['batch_id']}/publish/", {})[0] == 403
    checks.append('All three persisted batches retain their fixed configuration and independent reviewer')
    denied = principal('it')
    assert denied.request(root+f"batches/{legal['batch_id']}/")[0] == 403
    checks.append('IT cannot read imports without explicit financial permissions')
    inconsistent = c.execute("SELECT count(*) FROM aiced_integration.integration_store_journal j LEFT JOIN aiced_integration.integration_store_outbox o ON o.event_id=j.id WHERE j.action='imports.published' AND o.event_id IS NULL").fetchone()[0]
    assert inconsistent == 0
    checks.append('Publication journal retains corresponding transactional outbox events')

Path('/private/publication-rules-report.json').write_text(json.dumps({'status':'passed','checks':checks}, indent=2))
print('PASS:', len(checks), 'publication rule HTTP/SQL integration checks')
