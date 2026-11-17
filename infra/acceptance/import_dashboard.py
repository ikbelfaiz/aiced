"""Read-only SQL evidence for the three synthetic browser imports; test stack only."""
import hashlib,json
from pathlib import Path
import psycopg

private=Path('/private')
cfg=json.loads((private/'config.json').read_text())
# The isolated overlay uses its own volume/config; marker and synthetic org required too.
manifest=json.loads((private/'import-dashboard-manifest.json').read_text())
expected=json.loads((private/'import-dashboard-expected.json').read_text())
assert len(manifest)==3 and {x['template'] for x in manifest}=={'physical','legal','accounts'}
e=cfg['admin']
assert e['POSTGRES_DB']=='aiced_s7_disposable'
with psycopg.connect(host='db',dbname=e['POSTGRES_DB'],user=e['POSTGRES_USER'],password=e['POSTGRES_PASSWORD']) as c:
    assert c.execute("SELECT code FROM aiced_iam.identity_organization WHERE code='SYNTHETIC-A'").fetchone()
    fingerprints=[]
    for item in manifest:
        batch_id=item['batch_id'];template=item['template'];fixture=expected[template]
        batch=c.execute('SELECT status,digest,published_at,published_by_id,uploaded_by_id,policy_id,source_as_of FROM aiced_integration.ingestion_importbatch WHERE id=%s',[batch_id]).fetchone()
        assert batch[0]=='published' and batch[1]==fixture['digest'] and batch[2] and batch[3]!=batch[4]
        assert str(batch[5])==item['policy_id'] and str(batch[6])=='2026-03-01'
        rows=c.execute('SELECT r.cells,r.errors,r.normalized_dates,s.external_key FROM aiced_integration.ingestion_stagingrow r JOIN aiced_integration.ingestion_sourcesnapshot s ON s.row_id=r.id WHERE r.batch_id=%s',[batch_id]).fetchall()
        assert len(rows)==1
        cells,errors,dates,key=rows[0]
        assert cells==fixture['cells'] and errors==[] and key.startswith('SYNTH-REVIEW-')
        if template in ['physical','accounts']:assert dates['9']==('2000-01-02' if template=='physical' else '2024-01-02')
        assert c.execute('SELECT count(*) FROM public.clients_externalidentity WHERE external_id=%s',[key]).fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM public.clients_financialaccount WHERE external_id=%s',[key]).fetchone()[0]==0
        event=c.execute("SELECT j.id,o.event_id FROM aiced_integration.integration_store_journal j LEFT JOIN aiced_integration.integration_store_outbox o ON o.event_id=j.id WHERE j.target_id=%s AND j.action='imports.published'",[batch_id]).fetchall()
        assert len(event)==1 and event[0][0]==event[0][1]
        fingerprints.append(hashlib.sha256(json.dumps([list(batch),rows,event],default=str,sort_keys=True).encode()).hexdigest())
report={'status':'passed','templates':3,'fingerprints':fingerprints,'checks':['Exact PostgreSQL cells/digest/date normalization match synthetic workbook fixtures','Publisher differs from uploader; policy and source date retained','Exactly one immutable snapshot and publication journal/outbox per batch','Source keys absent from CRM external identities and financial accounts']}
baseline=private/'import-dashboard-sql.json'
if baseline.exists():
    old=json.loads(baseline.read_text())
    if old.get('batch_ids')==[x['batch_id'] for x in manifest]:assert old['fingerprints']==fingerprints,'Persisted source content changed'
report['batch_ids']=[x['batch_id'] for x in manifest]
baseline.write_text(json.dumps(report,indent=2))
print('PASS: three browser imports match PostgreSQL source snapshots, provenance and journal/outbox; no identity/account merge')
