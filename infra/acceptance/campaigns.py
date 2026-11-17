"""Actual gateway draft isolation, validation, races, rollback and IAM checks."""
import json,os,subprocess
from pathlib import Path
import sys
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
sys.path[:0]=['/app','/scripts']
import psycopg
from s3_rehearsal import Browser
cfg=json.loads(Path('/private/config.json').read_text());env=cfg['admin']
assert env['POSTGRES_DB']=='aiced_s7_disposable' and env['POSTGRES_HOST']=='db'
def db(name='admin'):
    e=cfg[name];return psycopg.connect(host='db',dbname=e['POSTGRES_DB'],user=e['POSTGRES_USER'],password=e['POSTGRES_PASSWORD'],autocommit=True)
with db() as c:assert c.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()[0]=='aiced-s7-synthetic-only'
run=uuid4().hex;role=uuid4();assignment=uuid4();checks=[];reviewer=None
base='/api/campaigns/'
try:
    with db() as c:
        member,org,reviewer=c.execute("SELECT m.id,m.organization_id,m.user_id FROM aiced_iam.identity_membership m JOIN aiced_iam.identity_user u ON u.id=m.user_id WHERE u.username='synthetic.reviewer.a'").fetchone()
        other_org=c.execute("SELECT id FROM aiced_iam.identity_organization WHERE code='SYNTHETIC-B'").fetchone()[0]
        c.execute("INSERT INTO aiced_iam.identity_role(id,code,name,is_active) VALUES(%s,%s,'SYNTHETIC campaign preparation',true)",[role,'s14-'+run])
        for code in ['opportunities.view','opportunities.manage']:c.execute('INSERT INTO aiced_iam.identity_role_permissions(role_id,capability_id) VALUES(%s,%s)',[role,code])
        c.execute("INSERT INTO aiced_iam.identity_roleassignment(id,membership_id,role_id,scope,is_active,created_at) VALUES(%s,%s,%s,'organization',true,now())",[assignment,member,role])
    owners=[Browser('http://gateway:8080'),Browser('http://gateway:8080')]
    for b in owners:b.login('synthetic.reviewer.a',env['AICED_SEED_PASSWORD'])
    other=Browser(owners[0].base);other.login('synthetic.operator.a',env['AICED_SEED_PASSWORD'])
    it=Browser(owners[0].base);it.login('synthetic.it.a',env['AICED_SEED_PASSWORD'])
    context=owners[0].request(base+'context/')[1]
    assert context['organizations']==[{'id':str(org),'name':'Organisation synthétique A'}]
    assert context['business_timezone']=='Africa/Tunis'
    payload={'organization_id':str(org),'name':'SYNTHETIC S14 '+run,'description':'Synthetic private draft','targeting_notes':'SYNTHETIC ONLY: criteria to discuss; never executed','planned_start':'2031-06-01','planned_end':'2031-06-02'}
    status,item,_=owners[0].request(base,payload);assert status==201,(status,item)
    ident=item['id'];url=base+ident+'/'
    assert item['status']=='draft' and item['creator_id']==str(reviewer) and item['version']==1
    assert other.request(url)[0]==404
    assert other.request(url,{'version':1,'name':'forged'},'PATCH')[0]==404
    assert other.request(base+'?search='+run)[1]['count']==0
    assert it.request(base)[0]==403 and it.request(base,payload)[0]==403
    assert owners[0].request(base,{**payload,'organization_id':str(other_org)})[0]==403
    checks.append('Private creator-only list/count/detail/update despite organization-wide grant; IT and foreign organization denied')
    for fields in [{'status':'active'},{'creator_id':str(uuid4())},{'client_ids':[str(uuid4())]},{'segment_id':str(uuid4())},{'recipients':['synthetic@example.invalid']},{'name':''},{'targeting_notes':'x'*2001},{'planned_end':'2031-05-31'}]:
        assert owners[0].request(base,{**payload,**fields})[0]==400,fields.keys()
    assert owners[0].request(url,{'version':1,'organization_id':str(org)},'PATCH')[0]==400
    assert owners[0].request(base+'?page_size=51')[0]==400
    assert owners[0].request(url,{},'DELETE')[0]==405
    assert owners[0].request(url,{'version':1,'planned_start':'2031-07-01'},'PATCH')[0]==400
    assert owners[0].request(base,payload,headers={'X-CSRFToken':'invalid'})[0]==403
    for i in range(8):assert owners[0].request(base,{**payload,'name':payload['name']+f' {i}'})[0]==201
    page=owners[0].request(base+'?search='+run+'&ordering=name')[1]
    assert page['count']==9 and len(page['results'])==8
    assert len(owners[0].request(base+'?search='+run+'&ordering=name&page=2')[1]['results'])==1
    checks.append('Strict fields, dates including partial update, CSRF, draft-only/no DELETE; scoped search/sort/pagination exact')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(b.request,url,{'version':1,'description':'SYNTHETIC race '+str(i)},'PATCH') for i,b in enumerate(owners)]
        assert sorted(f.result()[0] for f in futures)==[200,409]
    current=owners[0].request(url)[1];assert current['version']==2
    with db() as c:
        assert c.execute("SELECT count(*) FROM aiced_commercial.commercial_store_journal j JOIN aiced_commercial.commercial_store_outbox o ON o.event_id=j.id WHERE j.target_id=%s AND j.action='commercial.campaign_draft_saved'",[ident]).fetchone()[0]==2
    checks.append('Concurrent PATCH commits once; stale 409, version 2 and exactly create+edit journal/outbox pairs')
    for table,condition in [('commercial_store_journal',"IF NEW.action='commercial.campaign_draft_saved' THEN RAISE EXCEPTION 'SYNTHETIC journal failure'; END IF;"),('commercial_store_outbox',"RAISE EXCEPTION 'SYNTHETIC outbox failure';")]:
        with db() as c:
            before=c.execute('SELECT count(*) FROM aiced_commercial.commercial_store_campaigndraft').fetchone()[0]
            journal=c.execute('SELECT count(*) FROM aiced_commercial.commercial_store_journal').fetchone()[0]
            c.execute('CREATE FUNCTION aiced_commercial.s14_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN '+condition+' RETURN NEW; END $$')
            c.execute('CREATE TRIGGER s14_fail BEFORE INSERT ON aiced_commercial.'+table+' FOR EACH ROW EXECUTE FUNCTION aiced_commercial.s14_fail()')
        try:
            assert owners[0].request(base,payload)[0]==503
            assert owners[0].request(url,{'version':2,'description':'MUST ROLL BACK'},'PATCH')[0]==503
            with db() as c:
                assert c.execute('SELECT count(*) FROM aiced_commercial.commercial_store_campaigndraft').fetchone()[0]==before
                assert c.execute('SELECT count(*) FROM aiced_commercial.commercial_store_journal').fetchone()[0]==journal
                assert c.execute('SELECT version,description FROM aiced_commercial.commercial_store_campaigndraft WHERE id=%s',[ident]).fetchone()==(2,current['description'])
        finally:
            with db() as c:
                c.execute('DROP TRIGGER s14_fail ON aiced_commercial.'+table)
                c.execute('DROP FUNCTION aiced_commercial.s14_fail()')
    checks.append('Forced journal and outbox failures roll back creation, updates and versions; no partial audit')
    for name in ['iam','client','integration']:
        with db(name) as c:
            try:c.execute('SELECT * FROM aiced_commercial.commercial_store_campaigndraft LIMIT 0')
            except psycopg.errors.InsufficientPrivilege:pass
            else:raise AssertionError('Foreign service reads private drafts')
    with db('commercial') as c:
        assert not c.execute("SELECT has_table_privilege(current_user,'aiced_commercial.commercial_store_campaigndraft','DELETE')").fetchone()[0]
        try:c.execute('UPDATE aiced_commercial.commercial_store_campaigndraft SET creator_id=creator_id,organization_id=%s WHERE id=%s',[other_org,ident])
        except psycopg.errors.CheckViolation:pass
        else:raise AssertionError('Custody mutation permitted')
        try:c.execute("UPDATE aiced_commercial.commercial_store_campaigndraft SET status='active' WHERE id=%s",[ident])
        except psycopg.errors.CheckViolation:pass
        else:raise AssertionError('Non-draft database state permitted')
    checks.append('Existing Commercial schema owner and restricted roles; foreign SELECT/DELETE denied, custody/state DB constraints enforced')
    with db() as c:
        event=c.execute("SELECT id FROM aiced_commercial.commercial_store_journal WHERE target_id=%s AND action='commercial.campaign_draft_saved' ORDER BY occurred_at,id LIMIT 1",[ident]).fetchone()[0]
    delivery_env={**os.environ,**cfg['commercial'],'DJANGO_SETTINGS_MODULE':'commercial_service.settings','SSL_CERT_FILE':'/private/tls/ca.pem','S14_EVENT_ID':str(event)}
    # Simulate a lost acknowledgement for this synthetic event only, then replay.
    code="import os,django; django.setup(); from uuid import UUID; from commercial_service.delivery import deliver; from commercial_store.models import Outbox; event=UUID(os.environ['S14_EVENT_ID']); deliver(event); Outbox.objects.filter(event_id=event).update(delivered_at=None); deliver(event)"
    subprocess.run([sys.executable,'-c',code],env=delivery_env,check=True)
    with db() as c:
        receipts=c.execute("SELECT payload FROM aiced_iam.audit_auditreceipt WHERE producer='commercial' AND event_id=%s",[event]).fetchall()
        assert len(receipts)==1 and receipts[0][0]['action']=='commercial.campaign_draft_saved'
        assert not {'name','description','targeting_notes'} & set(receipts[0][0])
        assert c.execute('SELECT delivered_at IS NOT NULL FROM aiced_commercial.commercial_store_outbox WHERE event_id=%s',[event]).fetchone()[0]
    checks.append('Real signed campaign audit reaches IAM without draft content; lost acknowledgement replay creates exactly one receipt')
    with db() as c:c.execute("DELETE FROM aiced_iam.identity_role_permissions WHERE role_id=%s AND capability_id='opportunities.manage'",[role])
    assert not owners[0].request(url)[1]['can_edit']
    assert owners[0].request(url,{'version':2,'name':'forged'},'PATCH')[0] in [403,404]
    with db() as c:c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=false WHERE id=%s',[assignment])
    assert owners[0].request(base)[0]==403
    with db() as c:
        c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=true WHERE id=%s',[assignment])
        c.execute('UPDATE aiced_iam.identity_user SET is_active=false WHERE id=%s',[reviewer])
    assert owners[0].request(url)[0]==403
    assert owners[0].request(url,{'version':2,'description':'MUST NOT SAVE REVOKED USER'},'PATCH')[0]==403
    with db() as c:assert c.execute('SELECT version FROM aiced_commercial.commercial_store_campaigndraft WHERE id=%s',[ident]).fetchone()[0]==2
    with db() as c:c.execute('UPDATE aiced_iam.identity_user SET is_active=true WHERE id=%s',[reviewer])
    session=next(c.value for c in owners[1].jar if c.name=='sessionid')
    with db() as c:c.execute("UPDATE aiced_iam.django_session SET expire_date=now()-interval '1 minute' WHERE session_key=%s",[session])
    assert owners[1].request(base)[0]==403
    checks.append('Manage-only removal makes own draft read-only; role/user/session revocation blocks existing sessions')
finally:
    with db() as c:
        if reviewer:c.execute('UPDATE aiced_iam.identity_user SET is_active=true WHERE id=%s',[reviewer])
        c.execute('DELETE FROM aiced_iam.identity_roleassignment WHERE id=%s',[assignment])
        c.execute('DELETE FROM aiced_iam.identity_role_permissions WHERE role_id=%s',[role])
        c.execute('DELETE FROM aiced_iam.identity_role WHERE id=%s',[role])
Path('/private/campaigns-report.json').write_text(json.dumps({'status':'passed','checks':checks,'synthetic_fixture_run':run,'fixtures_retained':True},indent=2))
print('PASS: '+str(len(checks))+' actual campaign isolation/validation/concurrency/rollback/ACL/revocation checks')
