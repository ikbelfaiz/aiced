"""Synthetic-only real IAM and Nginx isolation checks; run apart from browsers."""
import json
from pathlib import Path
import sys
from uuid import uuid4
sys.path[:0]=['/app','/scripts']
import psycopg
from s3_rehearsal import Browser

cfg=json.loads(Path('/private/config.json').read_text())
env=cfg['admin']
def db():
    return psycopg.connect(host='db',dbname=env['POSTGRES_DB'],user=env['POSTGRES_USER'],password=env['POSTGRES_PASSWORD'],autocommit=True)

run=uuid4().hex
parties=[uuid4() for _ in range(3)]
member=None
active=None
checks=[]
try:
    with db() as c:
        with c.transaction():
            members=[c.execute('SELECT m.id,m.organization_id,m.is_active FROM aiced_iam.identity_membership m JOIN aiced_iam.identity_user u ON u.id=m.user_id WHERE u.username=%s',[name]).fetchone()
                     for name in ['synthetic.reader.a','synthetic.reviewer.a','synthetic.reader.b']]
            member,_,active=members[0]
            for index,(party,(assigned,org,_)) in enumerate(zip(parties,members)):
                c.execute("INSERT INTO public.clients_party(id,organization_id,kind,display_name,assigned_to_id,created_at,origin,version) VALUES(%s,%s,'physical',%s,%s,now(),'SYNTHETIC_ONLY',1)",[party,org,'SYNTHETIC S10 '+run,assigned])
                c.execute("INSERT INTO public.clients_physicalperson(party_id,first_name,last_name) VALUES(%s,'SYNTHETIC','SEGMENTATION')",[party])
                c.execute("INSERT INTO public.clients_crmprofile(party_id,notes,email,phone,profession,sector,version,updated_at) VALUES(%s,'','','',%s,%s,1,now())",[party,run+' profession '+str(index),run+' sector '+str(index)])
    b=Browser('http://gateway:8080'); b.login('synthetic.reader.a',env['AICED_SEED_PASSWORD'])
    status,data,_=b.request('/api/clients/filter-options/')
    assert status==200
    assert [v for v in data['profession']['values'] if run in v['value']]==[{'value':run+' profession 0','count':1}]
    assert [v for v in data['sector']['values'] if run in v['value']]==[{'value':run+' sector 0','count':1}]
    checks.append('Options/counts exclude same-organization unassigned and foreign-organization clients')
    from urllib.parse import urlencode
    for index in [1,2]:
        status,data,_=b.request('/api/clients/?'+urlencode({'profession':run+' profession '+str(index),'search':run,'page_size':1}))
        assert status==200 and data['count']==0
    checks.append('Forged hidden values cannot escape Client object scoping')
    with db() as c:c.execute('UPDATE aiced_iam.identity_membership SET is_active=false WHERE id=%s',[member])
    assert b.request('/api/clients/filter-options/')[0]==403
    assert b.request('/api/clients/?ordering=profession')[0]==403
    checks.append('Real IAM membership revocation denies both options and filtered list immediately')
    Path('/private/segmentation-report.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2))
    print('PASS: three real gateway/IAM segmentation visibility and revocation checks')
finally:
    with db() as c:
        with c.transaction():
            if member is not None:c.execute('UPDATE aiced_iam.identity_membership SET is_active=%s WHERE id=%s',[active,member])
            c.execute('DELETE FROM public.clients_crmprofile WHERE party_id=ANY(%s)',[parties])
            c.execute('DELETE FROM public.clients_physicalperson WHERE party_id=ANY(%s)',[parties])
            c.execute('DELETE FROM public.clients_party WHERE id=ANY(%s)',[parties])
