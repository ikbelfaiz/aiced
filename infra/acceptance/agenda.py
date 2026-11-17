"""Real IAM/Client owner-only agenda, writes, ACLs and revocation probes."""
import json
from pathlib import Path
import sys
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
sys.path[:0]=['/app','/scripts']
import psycopg
from s3_rehearsal import Browser
cfg=json.loads(Path('/private/config.json').read_text());env=cfg['admin']
def db(name='admin'):
    e=cfg[name];return psycopg.connect(host='db',dbname=e['POSTGRES_DB'],user=e['POSTGRES_USER'],password=e['POSTGRES_PASSWORD'],autocommit=True)
run=uuid4().hex;role=uuid4();assignments=[uuid4(),uuid4()];owner=None;checks=[]
try:
    with db() as c:
        people=[c.execute('SELECT m.id,m.organization_id,m.user_id FROM aiced_iam.identity_membership m JOIN aiced_iam.identity_user u ON u.id=m.user_id WHERE u.username=%s',[name]).fetchone() for name in ['synthetic.reader.a','synthetic.reviewer.a']]
        owner=people[0][2]
        c.execute("INSERT INTO aiced_iam.identity_role(id,code,name,is_active) VALUES(%s,%s,'SYNTHETIC agenda',true)",[role,'s12-'+run])
        for code in ['interactions.view','interactions.manage']:c.execute('INSERT INTO aiced_iam.identity_role_permissions(role_id,capability_id) VALUES(%s,%s)',[role,code])
        for assignment,(member,_,_) in zip(assignments,people):c.execute("INSERT INTO aiced_iam.identity_roleassignment(id,membership_id,role_id,scope,is_active,created_at) VALUES(%s,%s,%s,'organization',true,now())",[assignment,member,role])
    browsers=[Browser('http://gateway:8080') for _ in range(3)]
    for b,name in zip(browsers,['synthetic.reader.a','synthetic.reader.a','synthetic.reviewer.a']):b.login(name,env['AICED_SEED_PASSWORD'])
    payload={'organization_id':str(people[0][1]),'title':'SYNTHETIC S12 '+run,'kind':'call','date':'2031-05-04','start_time':'10:00','end_time':'11:00'}
    status,item,_=browsers[0].request('/api/agenda/',payload);assert status==201,(status,item)
    ident=item['id'];url='/api/agenda/'+ident+'/'
    status,other,_=browsers[2].request('/api/agenda/',{**payload,'title':'SYNTHETIC S12 SECRET '+run});assert status==201,(status,other)
    status,data,_=browsers[0].request('/api/agenda/?month=2031-05&search='+run)
    assert status==200 and data['count']==1 and data['days']=={'2031-05-04':1}
    assert browsers[0].request('/api/agenda/'+other['id']+'/')[0]==404
    assert browsers[0].request('/api/agenda/'+other['id']+'/',{'version':1,'title':'forged'},'PATCH')[0]==404
    checks.append('Real organization-wide CRM grant cannot reveal another owner appointment, count or calendar cell')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[pool.submit(b.request,url,{'version':1,'notes':'SYNTHETIC edit '+str(i)},'PATCH') for i,b in enumerate(browsers[:2])]
        assert sorted(f.result()[0] for f in results)==[200,409]
    with db() as c:
        assert c.execute("SELECT count(*) FROM public.audit_auditevent a JOIN public.audit_auditoutbox o ON o.event_id=a.id WHERE a.target_id=%s AND a.action='clients.appointments_saved'",[ident]).fetchone()[0]==2
        columns=c.execute("SELECT ccu.table_name FROM information_schema.constraint_column_usage ccu JOIN information_schema.table_constraints tc ON tc.constraint_name=ccu.constraint_name AND tc.constraint_schema=ccu.constraint_schema WHERE tc.table_schema='public' AND tc.table_name='clients_appointment' AND tc.constraint_type='FOREIGN KEY'").fetchall()
        assert {row[0] for row in columns}=={'iam_consumer_actorref','iam_consumer_organizationref'}
    checks.append('Simultaneous PATCH: one version increment/commit, one 409, exactly two journal/outbox pairs including create; only Client reference FKs')
    for name in ['iam','commercial','integration']:
        with db(name) as c:
            try:c.execute('SELECT * FROM public.clients_appointment LIMIT 0')
            except psycopg.errors.InsufficientPrivilege:pass
            else:raise AssertionError('Foreign service can read personal appointments')
    with db('client') as c:
        try:c.execute('UPDATE public.clients_appointment SET owner_id=%s WHERE id=%s',[people[1][2],ident])
        except psycopg.errors.CheckViolation:pass
        else:raise AssertionError('Owner mutation permitted')
        assert not c.execute("SELECT has_table_privilege(current_user,'public.clients_appointment','DELETE')").fetchone()[0]
    checks.append('Restricted runtime ACLs deny foreign schema reads and DELETE; DB trigger prevents owner reassignment')
    with db() as c:c.execute('UPDATE aiced_iam.identity_user SET is_active=false WHERE id=%s',[owner])
    assert browsers[0].request('/api/agenda/?month=2031-05')[0]==403
    assert browsers[0].request(url,{'version':2,'notes':'denied'},'PATCH')[0]==403
    checks.append('Actual IAM user deactivation denies agenda read and write immediately')
finally:
    with db() as c:
        with c.transaction():
            if owner:c.execute('UPDATE aiced_iam.identity_user SET is_active=true WHERE id=%s',[owner])
            c.execute('DELETE FROM aiced_iam.identity_roleassignment WHERE id=ANY(%s)',[assignments])
            c.execute('DELETE FROM aiced_iam.identity_role_permissions WHERE role_id=%s',[role])
            c.execute('DELETE FROM aiced_iam.identity_role WHERE id=%s',[role])
Path('/private/agenda-report.json').write_text(json.dumps({'status':'passed','checks':checks,'synthetic_fixture_run':run},indent=2))
print('PASS: four actual agenda owner/concurrency/audit/ACL/revocation checks')
