"""Synthetic gateway report oracle, visibility and live signed IAM revocation."""
import json,sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timedelta,timezone
sys.path[:0]=['/app','/scripts']
import psycopg
from s3_rehearsal import Browser
cfg=json.loads(Path('/private/config.json').read_text());env=cfg['admin']
assert env['POSTGRES_DB']=='aiced_s7_disposable' and env['POSTGRES_HOST']=='db'
def db():return psycopg.connect(host='db',dbname=env['POSTGRES_DB'],user=env['POSTGRES_USER'],password=env['POSTGRES_PASSWORD'],autocommit=True)
with db() as c:assert c.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()[0]=='aiced-s7-synthetic-only'
role=uuid4();assignment=uuid4();run=uuid4().hex;checks=[]
base='/api/clients/activity-report/?date_from=2024-05-17&date_to=2024-05-17'
try:
    with db() as c:
        member,org,user=c.execute("SELECT m.id,m.organization_id,m.user_id FROM aiced_iam.identity_membership m JOIN aiced_iam.identity_user u ON u.id=m.user_id WHERE u.username='synthetic.reader.a'").fetchone()
        c.execute("INSERT INTO aiced_iam.identity_role(id,code,name,is_active) VALUES(%s,%s,'SYNTHETIC reporting test',true)",[role,'s16-'+run])
        for code in ['interactions.view','prospects.view']:c.execute('INSERT INTO aiced_iam.identity_role_permissions(role_id,capability_id) VALUES(%s,%s)',[role,code])
        c.execute("INSERT INTO aiced_iam.identity_roleassignment(id,membership_id,role_id,scope,is_active,created_at) VALUES(%s,%s,%s,'assigned',true,now())",[assignment,member,role])
    op=Browser('http://gateway:8080');reader=Browser(op.base);it=Browser(op.base)
    for browser,name in [(op,'synthetic.operator.a'),(reader,'synthetic.reader.a'),(it,'synthetic.it.a')]:browser.login(name,env['AICED_SEED_PASSWORD'])
    own=reader.request('/api/clients/?page_size=1')[1]['results'][0]['id']
    before=reader.request(base);assert before[0]==200,before[:2]
    hidden=op.request('/api/clients/create/',{'organization_id':str(org),'kind':'physical','first_name':'SYNTHETIC','last_name':'S16 hidden '+run})
    assert hidden[0]==201;hidden_id=hidden[1]['id']
    for party in [own,hidden_id]:
        for stamp,kind in [('2024-05-16T22:59:59Z','visit'),('2024-05-16T23:00:00Z','call'),('2024-05-17T22:59:59Z','email'),('2024-05-17T23:00:00Z','visit')]:
            assert op.request(f'/api/clients/{party}/interactions/',{'kind':kind,'subject':'SYNTHETIC S16 '+run,'occurred_at':stamp})[0]==201
    after=reader.request(base);assert after[0]==200,after[:2]
    assert after[1]['interactions']['total']==before[1]['interactions']['total']+2
    assert after[1]['interactions']['daily'][0]['count']==after[1]['interactions']['total']
    assert reader.request(base+'&kind=call')[1]['interactions']['total']==before[1]['interactions']['by_kind']['call']+1
    with db() as c:
        oracle=c.execute("SELECT count(*) FROM public.clients_interaction i JOIN public.clients_party p ON p.id=i.party_id WHERE p.assigned_to_id=%s AND i.occurred_at >= '2024-05-16 23:00:00+00' AND i.occurred_at < '2024-05-17 23:00:00+00'",[member]).fetchone()[0]
    assert oracle==after[1]['interactions']['total']
    assert it.request(base)[0]==403
    checks.append('Exact PostgreSQL oracle, Tunis midnight inclusivity, kind filter, daily/card equality; hidden same-organization interactions excluded and IT denied')
    previous=op.request(base)[1]['appointments']['total']
    assert op.request('/api/agenda/',{'organization_id':str(org),'title':'SYNTHETIC S16 '+run,'kind':'meeting','date':'2024-05-17','start_time':'10:00','end_time':'11:00'})[0]==201
    assert op.request(base)[1]['appointments']['total']==previous+1
    assert reader.request(base)[1]['appointments']['total']==after[1]['appointments']['total']
    followups=reader.request('/api/prospects/follow-ups/')[1]['buckets']
    assert reader.request(base)[1]['followups']==followups
    for query in ['kind=bad','date_from=2024-01-01&date_to=2024-06-01']:
        assert reader.request('/api/clients/activity-report/?'+query)[0]==400
    checks.append('Personal appointment count and foreign-owner exclusion; current follow-up buckets equal the existing authorized worklist; invalid range/type denied')
    with db() as c:
        journals=c.execute('SELECT count(*) FROM public.audit_auditevent').fetchone()[0]
        outbox=c.execute('SELECT count(*) FROM public.audit_auditoutbox').fetchone()[0]
    assert reader.request(base)[0]==200
    with db() as c:
        assert c.execute('SELECT count(*) FROM public.audit_auditevent').fetchone()[0]==journals
        assert c.execute('SELECT count(*) FROM public.audit_auditoutbox').fetchone()[0]==outbox
    checks.append('Report is read-only and creates no business audit journal record')
    with db() as c:c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=false WHERE id=%s',[assignment])
    assert reader.request(base)[0]==403
    with db() as c:c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=true WHERE id=%s',[assignment])
    assert reader.request(base)[0]==200
    session=next(c.value for c in reader.jar if c.name=='sessionid')
    with db() as c:c.execute("UPDATE aiced_iam.django_session SET expire_date=now()-interval '1 minute' WHERE session_key=%s",[session])
    assert reader.request(base)[0]==403
    checks.append('Live role revocation and existing session expiry fail closed via Nginx/Client/signed IAM; permission recovery succeeds')
    Path('/private/activity-report.json').write_text(json.dumps({'status':'passed','checks':checks,'synthetic_oracle_total':oracle},indent=2))
    print('PASS:',len(checks),'commercial activity integration groups')
finally:
    with db() as c:
        c.execute('DELETE FROM aiced_iam.identity_roleassignment WHERE id=%s',[assignment])
        c.execute('DELETE FROM aiced_iam.identity_role_permissions WHERE role_id=%s',[role])
        c.execute('DELETE FROM aiced_iam.identity_role WHERE id=%s',[role])
