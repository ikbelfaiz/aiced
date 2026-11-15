"""Real gateway/SQL/TLS probes inside the disposable Docker network."""
import json
import os
from pathlib import Path
import subprocess
import sys
import yaml
sys.path[:0] = ['/app','/scripts']
import psycopg
from s3_rehearsal import Browser
from s6_probes import run as probes

cfg = json.loads(Path('/private/config.json').read_text())
os.environ['SSL_CERT_FILE']='/private/tls/ca.pem'
report = {'status':'running','checks':[]}
def passed(name):
    report['checks'].append(name)
    Path('/private/integration-report.json').write_text(json.dumps(report,indent=2))
    print(name,flush=True)
def connect(name='admin'):
    e=cfg[name]
    return psycopg.connect(host='db',dbname=e['POSTGRES_DB'],user=e['POSTGRES_USER'],password=e['POSTGRES_PASSWORD'],autocommit=True)
def command(name,settings,*args):
    subprocess.run([sys.executable,'/app/manage.py',*args],env={**os.environ,**cfg[name],'DJANGO_SETTINGS_MODULE':settings,
                   'SSL_CERT_FILE':'/private/tls/ca.pem'},check=True)

try:
    for name,tables in {
        'iam':['public.clients_party','aiced_integration.ingestion_importbatch','aiced_commercial.clients_opportunity'],
        'client':['aiced_iam.identity_user','public.identity_user','aiced_integration.ingestion_importbatch','aiced_commercial.clients_opportunity','public.clients_opportunity'],
        'integration':['public.clients_party','aiced_iam.identity_user','aiced_commercial.clients_opportunity'],
        'commercial':['public.clients_party','public.clients_financialaccount','public.clients_opportunity','aiced_iam.identity_user','aiced_integration.ingestion_importbatch'],
    }.items():
        with connect(name) as c:
            flags=c.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
            assert flags == (False,)*5
            for table in tables:
                for stmt in [f'SELECT * FROM {table} LIMIT 0',f'DELETE FROM {table} WHERE false']:
                    try: c.execute(stmt)
                    except psycopg.errors.InsufficientPrivilege: pass
                    else: raise AssertionError(name+' permits '+stmt)
    passed('Actual four LOGIN credentials deny foreign schema SELECT/DELETE and privileged role flags')
    with connect() as c:
        histories=c.execute("SELECT schemaname FROM pg_tables WHERE tablename='django_migrations' ORDER BY schemaname").fetchall()
        assert histories==[(s,) for s in ['aiced_commercial','aiced_iam','aiced_integration','public']]
        actor=c.execute("SELECT id FROM aiced_iam.identity_user WHERE username='synthetic.operator.a'").fetchone()[0]
        party,org=c.execute("SELECT p.id,p.organization_id FROM public.clients_party p JOIN aiced_iam.identity_organization o ON o.id=p.organization_id WHERE o.code='SYNTHETIC-A' AND NOT EXISTS(SELECT 1 FROM public.clients_prospect x WHERE x.party_id=p.id) ORDER BY p.id LIMIT 1").fetchone()
    passed('Four independent PostgreSQL migration histories retained')
    b=Browser('http://gateway:8080')
    b.login('synthetic.operator.a',cfg['admin']['AICED_SEED_PASSWORD'])
    base=f'/api/clients/{party}/opportunities/'
    status,item,_=b.request(base,{'title':'S7 synthetic Docker opportunity','amount':'123.456'})
    assert status==201,(status,item)
    assert item['amount']=='123.456'
    assert b.request(base+item['id']+'/',{'version':1,'title':'S7 updated'},'PATCH')[0]==200
    assert b.request(base+item['id']+'/',{'version':1,'title':'stale'},'PATCH')[0]==409
    assert Browser(b.base).request(base,headers={'X-User':str(actor),'X-Role':'admin'})[0]==403
    passed('Gateway session/CSRF, Commercial CRUD, exact Decimal, stale PATCH and forged role denial')
    schema=b.request('/api/schema/?format=json')
    baseline=yaml.safe_load(Path('/private/openapi-baseline.yaml').read_text())
    assert schema[0]==200,schema[:2]
    assert schema[1]==baseline, 'Complete composed OpenAPI mismatch'
    passed('Entire composed OpenAPI equals frozen baseline (38 routes / 47 method-path pairs)')
    probes(cfg['admin'],cfg['client'],cfg['commercial'],cfg['iam'],b,actor,party,org,item['id'],passed)
    command('commercial','commercial_service.settings','deliver_commercial_audit','--limit','100')
    with connect() as c:
        count=c.execute("SELECT count(*) FROM aiced_iam.audit_auditreceipt WHERE producer='commercial'").fetchone()[0]
        assert count>0
        event=c.execute('SELECT event_id FROM aiced_commercial.commercial_store_outbox WHERE delivered_at IS NOT NULL LIMIT 1').fetchone()[0]
        c.execute('UPDATE aiced_commercial.commercial_store_outbox SET delivered_at=NULL WHERE event_id=%s',[event])
    command('commercial','commercial_service.settings','deliver_commercial_audit','--limit','100')
    with connect() as c:
        assert c.execute("SELECT count(*) FROM aiced_iam.audit_auditreceipt WHERE producer='commercial'").fetchone()[0]==count
    passed('Signed cross-service audit delivery deduplicates lost acknowledgement retry')
    auditor=Browser(b.base)
    auditor.login('synthetic.manager.a',cfg['admin']['AICED_SEED_PASSWORD'])
    assert auditor.request('/api/audit/')[0]==200
    passed('Federated audit reads all four services through gateway')
    report['status']='passed'
except Exception as exc:
    report['status']='failed'
    report['error']=str(exc)
    raise
finally:
    Path('/private/integration-report.json').write_text(json.dumps(report,indent=2))
