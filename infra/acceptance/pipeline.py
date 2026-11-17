"""Synthetic real gateway pipeline scope, concurrency and revocation checks."""
import json
from pathlib import Path
import sys
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
sys.path[:0]=['/app','/scripts']
import psycopg
from s3_rehearsal import Browser

cfg=json.loads(Path('/private/config.json').read_text());env=cfg['admin']
def db():return psycopg.connect(host='db',dbname=env['POSTGRES_DB'],user=env['POSTGRES_USER'],password=env['POSTGRES_PASSWORD'],autocommit=True)
run=uuid4().hex
parties=[uuid4() for _ in range(3)]
opps=[uuid4() for _ in range(5)]
role,assignment=uuid4(),uuid4()
checks=[]
try:
    with db() as c:
        with c.transaction():
            people=[c.execute('SELECT m.id,m.organization_id,m.user_id FROM aiced_iam.identity_membership m JOIN aiced_iam.identity_user u ON u.id=m.user_id WHERE u.username=%s',[name]).fetchone() for name in ['synthetic.reader.a','synthetic.reviewer.a','synthetic.reader.b']]
            actor=c.execute("SELECT id FROM aiced_iam.identity_user WHERE username='synthetic.operator.a'").fetchone()[0]
            c.execute("INSERT INTO aiced_commercial.commercial_store_actorref(id,username) VALUES(%s,'synthetic.operator.a') ON CONFLICT DO NOTHING",[actor])
            c.execute("INSERT INTO aiced_iam.identity_role(id,code,name,is_active) VALUES(%s,%s,'SYNTHETIC pipeline role',true)",[role,'s11-'+run])
            c.execute("INSERT INTO aiced_iam.identity_role_permissions(role_id,capability_id) VALUES(%s,'opportunities.view')",[role])
            c.execute("INSERT INTO aiced_iam.identity_roleassignment(id,membership_id,role_id,scope,is_active,created_at) VALUES(%s,%s,%s,'assigned',true,now())",[assignment,people[0][0],role])
            for i,(party,(member,org,_)) in enumerate(zip(parties,people)):
                c.execute("INSERT INTO public.clients_party(id,organization_id,kind,display_name,assigned_to_id,created_at,origin,version) VALUES(%s,%s,'physical',%s,%s,now(),'SYNTHETIC_ONLY',1)",[party,org,run+' SYNTHETIC '+str(i),member])
                c.execute("INSERT INTO public.clients_physicalperson(party_id,first_name,last_name) VALUES(%s,'SYNTHETIC','PIPELINE')",[party])
                c.execute('INSERT INTO aiced_commercial.commercial_store_partyref(id,organization_id) VALUES(%s,%s)',[party,org])
            for i,ident in enumerate(opps):
                party=parties[0] if i<3 else parties[i-2]
                status=['open','won','lost','open','won'][i]
                c.execute("INSERT INTO aiced_commercial.clients_opportunity(id,party_id,title,notes,amount,currency,status,due_date,author_id,version,updated_at) VALUES(%s,%s,%s,'SYNTHETIC pipeline fixture',123.456,'TND',%s,NULL,%s,1,now())",[ident,party,run+' '+str(i),status,actor])
    reader=Browser('http://gateway:8080');reader.login('synthetic.reader.a',env['AICED_SEED_PASSWORD'])
    base='/api/opportunities/?'+urlencode({'search':run,'page_size':1,'ordering':'title'})
    status,data,_=reader.request(base)
    assert status==200 and data['count']==3,(status,data)
    assert data['statuses']=={'open':1,'won':1,'lost':1}
    assert data['results'][0]['id']==str(opps[0]) and not data['results'][0]['can_edit']
    assert reader.request(base+'&page=2')[1]['results'][0]['id']==str(opps[1])
    assert reader.request(base+'&status=lost')[1]['results'][0]['id']==str(opps[2])
    assert reader.request('/api/opportunities/?search='+run+'%203')[1]['count']==0
    checks.append('Assigned scope excludes same-org unassigned and foreign-org rows before counts/status summaries/pages/search')
    for query in ['status=bad','ordering=bad','page_size=51','page=0','search='+'x'*201]:assert reader.request('/api/opportunities/?'+query)[0]==400
    checks.append('Filters validated and stable title/status pagination verified')
    operators=[Browser(reader.base),Browser(reader.base)]
    for operator in operators:operator.login('synthetic.operator.a',env['AICED_SEED_PASSWORD'])
    url=f'/api/clients/{parties[0]}/opportunities/{opps[0]}/'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(op.request,url,{'version':1,'status':status},'PATCH') for op,status in zip(operators,['won','lost'])]
        responses=[f.result() for f in futures]
    assert sorted(r[0] for r in responses)==[200,409]
    item=operators[0].request(url)[1]
    assert item['version']==2
    with db() as c:
        assert c.execute("SELECT count(*) FROM aiced_commercial.commercial_store_journal j JOIN aiced_commercial.commercial_store_outbox o ON o.event_id=j.id WHERE j.target_id=%s AND j.action='clients.opportunities_saved'",[opps[0]]).fetchone()[0]==1
    assert reader.request(base)[1]['statuses']['open']==0
    checks.append('Two real simultaneous existing PATCH requests yield one commit/version increment/journal+outbox and one stale 409; pipeline reflects status')
    assert reader.request(url,{'version':2,'status':'open'},'PATCH')[0] in [403,404]
    with db() as c:c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=false WHERE id=%s',[assignment])
    assert reader.request('/api/opportunities/')[0]==403
    checks.append('View-only user cannot transition; real IAM role revocation blocks next pipeline request')
    expired=operators[0]
    session=next(cookie.value for cookie in expired.jar if cookie.name=='sessionid')
    with db() as c:c.execute("UPDATE aiced_iam.django_session SET expire_date=now()-interval '1 minute' WHERE session_key=%s",[session])
    assert expired.request('/api/opportunities/')[0]==403
    checks.append('Expired actual IAM session cannot read pipeline')
finally:
    with db() as c:
        with c.transaction():
            # Commercial references are intentionally immutable. Retain labeled
            # synthetic fixture records and journals in this disposable DB.
            c.execute('DELETE FROM aiced_iam.identity_roleassignment WHERE id=%s',[assignment])
            c.execute('DELETE FROM aiced_iam.identity_role_permissions WHERE role_id=%s',[role])
            c.execute('DELETE FROM aiced_iam.identity_role WHERE id=%s',[role])
Path('/private/pipeline-report.json').write_text(json.dumps({'status':'passed','checks':checks,'synthetic_fixture_run':run,'fixtures_retained':True},indent=2))
print('PASS: five real pipeline scope/filter/concurrent-write/audit/revocation/session checks')
