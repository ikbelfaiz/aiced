"""Actual IAM-snapshot/object-scope checks for the new history through Nginx."""
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
                for name in ['synthetic.reader.a','synthetic.reviewer.a','synthetic.reader.b','synthetic.operator.a']}
            actor=people['synthetic.operator.a'][2]
            c.execute('INSERT INTO public.iam_consumer_actorref(id,username) VALUES(%s,%s) ON CONFLICT DO NOTHING',[actor,'synthetic.operator.a'])
            c.execute('INSERT INTO aiced_iam.identity_role(id,code,name,is_active) VALUES(%s,%s,%s,true)',[role,'s8-history-'+run,'SYNTHETIC history isolation'])
            c.execute('INSERT INTO aiced_iam.identity_role_permissions(role_id,capability_id) VALUES(%s,%s)',[role,'interactions.view'])
            c.execute("INSERT INTO aiced_iam.identity_roleassignment(id,membership_id,role_id,scope,is_active,created_at) VALUES(%s,%s,%s,'assigned',true,now())",[assignment,people['synthetic.reader.a'][0],role])
            for party,name in zip(parties,['synthetic.reader.a','synthetic.reviewer.a','synthetic.reader.b']):
                member,org,_=people[name]
                c.execute("INSERT INTO public.clients_party(id,organization_id,kind,display_name,assigned_to_id,created_at,origin,version) VALUES(%s,%s,'physical',%s,%s,now(),'SYNTHETIC_ONLY',1)",[party,org,'SYNTHETIC S8 '+run,member])
                c.execute("INSERT INTO public.clients_physicalperson(party_id,first_name,last_name) VALUES(%s,'SYNTHETIC','HISTORY')",[party])
                c.execute("INSERT INTO public.clients_interaction(id,party_id,kind,subject,notes,occurred_at,author_id,version,updated_at) VALUES(%s,%s,'call',%s,'Synthetic isolated notes',now(),%s,1,now())",[uuid4(),party,run,actor])
    b=Browser('http://gateway:8080');b.login('synthetic.reader.a',e['AICED_SEED_PASSWORD'])
    data=b.request('/api/interactions/?search='+run)
    assert data[0]==200 and data[1]['count']==1,data[:2]
    assert data[1]['results'][0]['party_id']==str(parties[0])
    checks.append('Real IAM assigned grants intersect clients/interactions on the same object before count/search')
    for party in parties[1:]:
        result=b.request('/api/interactions/?party_id='+str(party))
        assert result[0]==200 and result[1]['count']==0
    checks.append('Same-organization unassigned and foreign-organization IDs reveal no rows or counts')
    with db() as c:c.execute('INSERT INTO public.clients_prospect(party_id,source,status,next_action,next_action_date,version,updated_at) VALUES(%s,%s,%s,%s,NULL,1,now())',[parties[0],'SYNTHETIC','contact',''])
    assert b.request('/api/interactions/?search='+run)[1]['count']==0
    checks.append('Prospect permission required through the actual remote grant contract')
    with db() as c:
        c.execute('DELETE FROM public.clients_prospect WHERE party_id=%s',[parties[0]])
        c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=false WHERE id=%s',[assignment])
    assert b.request('/api/interactions/')[0]==403
    checks.append('IAM role revocation denies the next real gateway request without cached history')
    Path('/private/history-report.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2))
    print('PASS: four real gateway/IAM history isolation and revocation checks')
finally:
    with db() as c:
        with c.transaction():
            c.execute('DELETE FROM public.clients_interaction WHERE party_id=ANY(%s)',[parties])
            c.execute('DELETE FROM public.clients_prospect WHERE party_id=ANY(%s)',[parties])
            c.execute('DELETE FROM public.clients_physicalperson WHERE party_id=ANY(%s)',[parties])
            c.execute('DELETE FROM public.clients_party WHERE id=ANY(%s)',[parties])
            c.execute('DELETE FROM aiced_iam.identity_roleassignment WHERE id=%s',[assignment])
            c.execute('DELETE FROM aiced_iam.identity_role_permissions WHERE role_id=%s',[role])
            c.execute('DELETE FROM aiced_iam.identity_role WHERE id=%s',[role])
