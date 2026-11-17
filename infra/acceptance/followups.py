"""Actual IAM-snapshot/object-scope checks for the prospect follow-ups through Nginx."""
import json
from pathlib import Path
import sys
from uuid import uuid4
sys.path[:0]=['/app','/scripts']
import psycopg
from s3_rehearsal import Browser

cfg=json.loads(Path('/private/config.json').read_text())
e=cfg['admin']
def db():
    return psycopg.connect(host='db',dbname=e['POSTGRES_DB'],user=e['POSTGRES_USER'],password=e['POSTGRES_PASSWORD'],autocommit=True)
run=uuid4().hex
role,assignment=uuid4(),uuid4()
parties=[uuid4() for _ in range(3)]
checks=[]
try:
    with db() as c:
        with c.transaction():
            people={name:c.execute('SELECT m.id,m.organization_id,m.user_id FROM aiced_iam.identity_membership m JOIN aiced_iam.identity_user u ON u.id=m.user_id WHERE u.username=%s',[name]).fetchone()
                for name in ['synthetic.reader.a','synthetic.reviewer.a','synthetic.reader.b']}
            c.execute('INSERT INTO aiced_iam.identity_role(id,code,name,is_active) VALUES(%s,%s,%s,true)',[role,'s9-followups-'+run,'SYNTHETIC follow-up isolation'])
            c.execute('INSERT INTO aiced_iam.identity_role_permissions(role_id,capability_id) VALUES(%s,%s)',[role,'prospects.view'])
            c.execute("INSERT INTO aiced_iam.identity_roleassignment(id,membership_id,role_id,scope,is_active,created_at) VALUES(%s,%s,%s,'assigned',true,now())",[assignment,people['synthetic.reader.a'][0],role])
            for party,name in zip(parties,['synthetic.reader.a','synthetic.reviewer.a','synthetic.reader.b']):
                member,org,_=people[name]
                c.execute("INSERT INTO public.clients_party(id,organization_id,kind,display_name,assigned_to_id,created_at,origin,version) VALUES(%s,%s,'physical',%s,%s,now(),'SYNTHETIC_ONLY',1)",[party,org,'SYNTHETIC S9 '+run,member])
                c.execute("INSERT INTO public.clients_physicalperson(party_id,first_name,last_name) VALUES(%s,'SYNTHETIC','FOLLOWUP')",[party])
                c.execute("INSERT INTO public.clients_prospect(party_id,source,status,next_action,next_action_date,version,updated_at) VALUES(%s,%s,'contact','Synthetic follow-up',NULL,1,now())",[party,run])
    b=Browser('http://gateway:8080');b.login('synthetic.reader.a',e['AICED_SEED_PASSWORD'])
    data=b.request('/api/prospects/follow-ups/?search='+run+'&bucket=unscheduled&page_size=1')
    assert data[0]==200 and data[1]['count']==1,data[:2]
    assert data[1]['results'][0]['id']==str(parties[0])
    assert sum(data[1]['buckets'].values())==1
    assert b.request('/api/prospects/follow-ups/?search='+run+'&page_size=1&page=2')[0]==404
    checks.append('Real IAM assigned scope before counts, buckets and pagination')
    with db() as c:
        c.execute("UPDATE aiced_iam.identity_roleassignment SET scope='organization' WHERE id=%s",[assignment])
    data=b.request('/api/prospects/follow-ups/?search='+run)
    assert data[0]==200 and data[1]['count']==1
    checks.append('Broader prospect grant still intersects assigned clients.view on the same object')
    with db() as c:
        c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=false WHERE id=%s',[assignment])
    assert b.request('/api/prospects/follow-ups/')[0]==403
    checks.append('IAM revocation immediately denies the next gateway request')
    Path('/private/followups-report.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2))
    print('PASS: three real gateway/IAM follow-up scope and revocation checks')
finally:
    with db() as c:
        with c.transaction():
            c.execute('DELETE FROM public.clients_prospect WHERE party_id=ANY(%s)',[parties])
            c.execute('DELETE FROM public.clients_physicalperson WHERE party_id=ANY(%s)',[parties])
            c.execute('DELETE FROM public.clients_party WHERE id=ANY(%s)',[parties])
            c.execute('DELETE FROM aiced_iam.identity_roleassignment WHERE id=%s',[assignment])
            c.execute('DELETE FROM aiced_iam.identity_role_permissions WHERE role_id=%s',[role])
            c.execute('DELETE FROM aiced_iam.identity_role WHERE id=%s',[role])
