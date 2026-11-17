"""Synthetic-only live Gateway/IAM/source contract and SQL invariant probes."""
import json,os,sys
from pathlib import Path
from uuid import uuid4
sys.path[:0]=['/app','/scripts']
import psycopg
from s3_rehearsal import Browser
from internal_api.security import signed_headers

cfg=json.loads(Path('/private/config.json').read_text());env=cfg['admin']
assert env['POSTGRES_DB']=='aiced_s7_disposable' and env['POSTGRES_HOST']=='db'
os.environ['SSL_CERT_FILE']='/private/tls/ca.pem'
def db(name='admin'):
    e=cfg[name]
    return psycopg.connect(host='db',dbname=e['POSTGRES_DB'],user=e['POSTGRES_USER'],password=e['POSTGRES_PASSWORD'],autocommit=True)
with db() as c:
    assert c.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()[0]=='aiced-s7-synthetic-only'
role=uuid4();assignment=uuid4();checks=[]
try:
    with db() as c:
        member,org,user=c.execute("SELECT m.id,m.organization_id,m.user_id FROM aiced_iam.identity_membership m JOIN aiced_iam.identity_user u ON u.id=m.user_id WHERE u.username='synthetic.reader.a'").fetchone()
        c.execute("INSERT INTO aiced_iam.identity_role(id,code,name,is_active) VALUES(%s,%s,'SYNTHETIC source preparation',true)",[role,'source-'+uuid4().hex])
        for code in ['imports.view','clients.view_financial']:
            c.execute('INSERT INTO aiced_iam.identity_role_permissions(role_id,capability_id) VALUES(%s,%s)',[role,code])
        c.execute("INSERT INTO aiced_iam.identity_roleassignment(id,membership_id,role_id,scope,is_active,created_at) VALUES(%s,%s,%s,'organization',true,now())",[assignment,member,role])
    reader=Browser('http://gateway:8080');it=Browser(reader.base)
    for browser,name in [(reader,'synthetic.reader.a'),(it,'synthetic.it.a')]:browser.login(name,env['AICED_SEED_PASSWORD'])
    own=reader.request('/api/clients/?page_size=1')[1]['results'][0]['id']
    with db() as c:
        hidden=str(c.execute('SELECT id FROM public.clients_party WHERE organization_id=%s AND assigned_to_id IS DISTINCT FROM %s AND id NOT IN(SELECT party_id FROM public.clients_prospect) LIMIT 1',[org,member]).fetchone()[0])
    url=f'/api/clients/{own}/source-mapping-preview/'
    def invariant():
        with db() as c:
            return [c.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ['public.clients_party','public.clients_externalidentity','public.clients_financialaccount','aiced_integration.ingestion_sourcesnapshot','public.audit_auditevent','public.audit_auditoutbox','aiced_integration.integration_store_journal','aiced_integration.integration_store_outbox']]
    before=invariant()
    cases=[('unique','candidate_unique',1),('ambiguous','ambiguous_candidate',1),('missing','missing_identifier',1),('duplicate','duplicate_identifier',2),('multiple_accounts','candidate_unique',2),('conflicting_identifiers','conflicting_identifiers',1)]
    for scenario,status,count in cases:
        response,data,_=reader.request(url+'?scenario='+scenario)
        assert response==200,(scenario,response,data)
        assert data['mode']=='synthetic' and data['mapping_approved'] is False and data['real_source_access'] is False and data['relationships_persisted'] is False
        assert len(data['relationships'])==count and {x['status'] for x in data['relationships']}=={status}
        assert all(x['confirmed'] is False for x in data['relationships'])
        assert all(x['provenance']['publication_state']=='illustrative_fixture_not_a_published_import' for x in data['records'])
    assert invariant()==before
    checks.append('Six candidate cases, no confirmed identities; unchanged Party/ExternalIdentity/FinancialAccount/snapshot and journal/outbox counts on successful reads')
    for browser,path in [(reader,f'/api/clients/{hidden}/source-mapping-preview/'),(it,url)]:
        status,data,_=browser.request(path)
        assert status in [403,404] and 'records' not in data
    assert reader.request(url+'?mode=published')[0]==400
    checks.append('Client object visibility and IT deny before candidates; public API cannot switch to real-source mode')
    session=next(c.value for c in reader.jar if c.name=='sessionid')
    private='/internal/v1/source-mapping/preview'
    payload={'credentials':{'session_key':session,'method':'GET','host':'gateway:8080','scheme':'http'},'actor_id':str(user),'organization_id':str(org),'party_id':own,'mode':'synthetic','scenario':'unique'}
    key=cfg['keys']['client-integration-v1']['secret']
    source=Browser('https://integration:8444')
    body=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    headers=signed_headers('client-integration-v1',key,'integration',private,body)
    assert source.request(private,body,headers=headers)[0]==200
    assert source.request(private,body,headers=headers)[0]==403
    assert source.request(private,body,headers={**headers,'X-Aiced-Nonce':'b'*48})[0]==403
    payload['mode']='published';body=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    status,data,_=source.request(private,body,headers=signed_headers('client-integration-v1',key,'integration',private,body))
    assert status==403 and 'records' not in data
    checks.append('Actual signed TLS source route accepts synthetic; rejects replay/forgery and denies published reads even with valid service/user credentials')
    for fence in [4711239301896721,591445740000006]:
        with db() as c:
            c.execute('BEGIN');c.execute('SELECT pg_advisory_xact_lock(%s)',[fence])
            try:
                status,data,_=reader.request(url)
                assert status==503 and 'records' not in data
            finally:c.execute('ROLLBACK')
    checks.append('Exclusive IAM and Client admission fences cause fail-closed 503, no stale candidate payload')
    with db() as c:
        with c.transaction():
            c.execute('SELECT pg_advisory_xact_lock(%s)',[4711239301896721])
            c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=false WHERE id=%s',[assignment])
    assert reader.request(url)[0]==403
    with db() as c:c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=true WHERE id=%s',[assignment])
    assert reader.request(url)[0]==200
    with db() as c:
        with c.transaction():
            c.execute('SELECT pg_advisory_xact_lock(%s)',[4711239301896721])
            c.execute("DELETE FROM aiced_iam.identity_role_permissions WHERE role_id=%s AND capability_id='imports.view'",[role])
    status,data,_=reader.request(url)
    assert status==403 and 'records' not in data
    with db() as c:c.execute("INSERT INTO aiced_iam.identity_role_permissions(role_id,capability_id) VALUES(%s,'imports.view')",[role])
    assert reader.request(url)[0]==200
    checks.append('Existing-session IAM role revocation and Integration-owned import-only revocation both deny; restored permission recovers without widening Client grant snapshots')
    with db('integration') as c:
        snapshot=c.execute('SELECT id FROM aiced_integration.ingestion_sourcesnapshot LIMIT 1').fetchone()
        assert snapshot,'Run existing synthetic import fixture first'
        c.execute('BEGIN')
        try:
            try:c.execute("UPDATE aiced_integration.ingestion_sourcesnapshot SET external_key='SYNTH-FORBIDDEN-MUTATION' WHERE id=%s",[snapshot[0]])
            except (psycopg.errors.InsufficientPrivilege,psycopg.errors.CheckViolation):pass
            else:raise AssertionError('Snapshot mutation allowed')
        finally:c.execute('ROLLBACK')
    checks.append('Runtime still cannot mutate existing published synthetic snapshots; preview fixture does not claim actual publication provenance')
    Path('/private/source-mapping-report.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2))
    print('PASS:',len(checks),'source mapping integration groups')
finally:
    with db() as c:
        c.execute('DELETE FROM aiced_iam.identity_roleassignment WHERE id=%s',[assignment])
        c.execute('DELETE FROM aiced_iam.identity_role_permissions WHERE role_id=%s',[role])
        c.execute('DELETE FROM aiced_iam.identity_role WHERE id=%s',[role])
