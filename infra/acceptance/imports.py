"""Gateway import validation/review/publication/idempotency on synthetic cells."""
import json
import os
from pathlib import Path
import sys
import uuid
sys.path[:0]=['/app','/scripts']
from s3_rehearsal import Browser,workbook
import psycopg
cfg=json.loads(Path('/private/config.json').read_text())
def connect(name):
    e=cfg[name]
    return psycopg.connect(host='db',dbname=e['POSTGRES_DB'],user=e['POSTGRES_USER'],password=e['POSTGRES_PASSWORD'],autocommit=True)
with connect('admin') as c:
    org=str(c.execute("SELECT id FROM aiced_iam.identity_organization WHERE code='SYNTHETIC-A'").fetchone()[0])
operator=Browser('http://gateway:8080')
reviewer=Browser(operator.base)
for b,user in [(operator,'operator'),(reviewer,'reviewer')]:
    b.login('synthetic.'+user+'.a',cfg['admin']['AICED_SEED_PASSWORD'])
root=f'/api/imports/{org}/'
upload=root+'upload/?template=legal&source_as_of=2026-01-01&date_format=ISO&snapshot_kind=partial'
content=workbook('S7-'+uuid.uuid4().hex)
code,data,_=operator.request(upload,content,headers={'Content-Type':'application/octet-stream'})
assert code==201,(code,data)
batch=data['id']
replay=operator.request(upload,content,headers={'Content-Type':'application/octet-stream'})
assert replay[0]==200 and replay[1]['id']==batch
url=root+f'batches/{batch}/'
preview=operator.request(url)
assert preview[0]==200 and preview[1]['batch']['rejected']==2
csv=operator.request(url+'rejections/')
assert csv[0]==200 and csv[2]['Content-Type'].startswith('text/csv') and 'attachment' in csv[2]['Content-Disposition']
code,policy,_=operator.request(root+'policies/',{'template':'legal','key_column':2,'rationale':'S7 SYNTHETIC explicit immutable snapshot publication review'})
assert code==201,(code,policy)
pid=policy['id']
assert operator.request(root+f'policies/{pid}/approve/',{},'POST')[0]==403
assert reviewer.request(root+f'policies/{pid}/approve/',{},'POST')[0]==200
assert operator.request(url+'publish/',{'policy_id':pid,'skip_rejected':True})[0]==403
published=reviewer.request(url+'publish/',{'policy_id':pid,'skip_rejected':True})
assert published[0]==200 and published[1]['published_rows']==1,published[:2]
again=reviewer.request(url+'publish/',{'policy_id':pid,'skip_rejected':True})
assert again[0]==200,again[:2]
with connect('admin') as c:
    assert c.execute('SELECT count(*) FROM aiced_integration.ingestion_sourcesnapshot s JOIN aiced_integration.ingestion_stagingrow r ON r.id=s.row_id WHERE r.batch_id=%s',[batch]).fetchone()[0]==1
with connect('integration') as c:
    try:
        c.execute('DELETE FROM aiced_integration.ingestion_sourcesnapshot WHERE row_id IN (SELECT id FROM aiced_integration.ingestion_stagingrow WHERE batch_id=%s)',[batch])
    except psycopg.errors.InsufficientPrivilege: pass
    else: raise AssertionError('Runtime can delete immutable snapshot')
Path('/private/import-report.json').write_text(json.dumps({'status':'passed','checks':[
    'raw XLSX upload, validation, duplicate rejection, CSV download',
    'upload idempotency returns the same batch',
    'two-actor policy approval and publisher authorization',
    'reviewed partial snapshot publication and publication idempotency',
    'one immutable snapshot; runtime DELETE denied']},indent=2))
Path('/private/import-browser-state.json').write_text(json.dumps({'batch_id':batch,'uploader':{'username':'synthetic.operator.a'},
    'reviewer':{'username':'synthetic.reviewer.a'},'it':{'username':'synthetic.it.a'}}))
print('PASS: gateway imports, two-actor review, immutable publication, replay and CSV')
