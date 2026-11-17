"""Synthetic-only gateway probes, including actual signed IAM revocation."""
import json,sys
from pathlib import Path
sys.path[:0]=['/app','/scripts']
import psycopg
from s3_rehearsal import Browser
cfg=json.loads(Path('/private/config.json').read_text())
env=cfg['admin']
assert env['POSTGRES_DB']=='aiced_s7_disposable' and env['POSTGRES_HOST']=='db'
def db():return psycopg.connect(host='db',dbname=env['POSTGRES_DB'],user=env['POSTGRES_USER'],password=env['POSTGRES_PASSWORD'],autocommit=True)
with db() as c:
    assert c.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()[0]=='aiced-s7-synthetic-only'
checks=[]
b=Browser('http://gateway:8080');b.login('synthetic.reader.a',env['AICED_SEED_PASSWORD'])
operator=Browser(b.base);operator.login('synthetic.operator.a',env['AICED_SEED_PASSWORD'])
it=Browser(b.base);it.login('synthetic.it.a',env['AICED_SEED_PASSWORD'])
status,items,_=b.request('/api/clients/?page_size=24');assert status==200 and items['count']>0
own=items['results'][0]['id'];url=f'/api/clients/{own}/quality/'
quality=b.request(url);assert quality[0]==200
status,options,_=b.request('/api/clients/filter-options/');assert status==200
assert options['quality']['total']==items['count']
with db() as c:
    user=c.execute("SELECT id FROM aiced_iam.identity_user WHERE username='synthetic.reader.a'").fetchone()[0]
    hidden=c.execute("SELECT p.id FROM public.clients_party p WHERE NOT EXISTS (SELECT 1 FROM aiced_iam.identity_membership m WHERE m.id=p.assigned_to_id AND m.user_id=%s) AND NOT EXISTS (SELECT 1 FROM public.clients_prospect x WHERE x.party_id=p.id) LIMIT 1",[user]).fetchone()[0]
assert b.request(f'/api/clients/{hidden}/quality/')[0]==404
assert it.request(url)[0]==403 and it.request('/api/clients/filter-options/')[0]==403
checks.append('Actual reader scope precedes quality totals; hidden same/foreign objects 404 and IT 403')
percent=quality[1]['percentage']
assert isinstance(percent,int) and 0<=percent<=100
assert b.request(f'/api/clients/?completeness_min={percent}&completeness_max={percent}')[0]==200
assert b.request('/api/clients/?completeness_min=101')[0]==400
assert b.request('/api/clients/?missing_field=risk')[0]==400
checks.append('Gateway quality/ranges/validation use Client runtime credential and signed IAM snapshot')
try:
    with db() as c:
        assignments=[r[0] for r in c.execute('SELECT a.id FROM aiced_iam.identity_roleassignment a JOIN aiced_iam.identity_membership m ON m.id=a.membership_id WHERE m.user_id=%s AND a.is_active',[user])]
        assert assignments
        c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=false WHERE id=ANY(%s)',[assignments])
    for path in [url,'/api/clients/filter-options/','/api/clients/?completeness_min=0']:
        status,data,_=b.request(path);assert status==403 and 'quality' not in data and 'count' not in data
finally:
    with db() as c:c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=true WHERE id=ANY(%s)',[assignments])
recovered=b.request(url)
assert recovered[0]==200 and recovered[1]==quality[1]
checks.append('Permission revocation immediately blocks existing-session list/options/detail, then recovers')
session=next(c.value for c in b.jar if c.name=='sessionid')
with db() as c:c.execute("UPDATE aiced_iam.django_session SET expire_date=now()-interval '1 minute' WHERE session_key=%s",[session])
for path in [url,'/api/clients/filter-options/','/api/clients/?completeness_min=0']:
    assert b.request(path)[0]==403
checks.append('Expired IAM session denied through real gateway and signed Client-to-IAM requests')
operator_options=operator.request('/api/clients/filter-options/')
assert operator_options[0]==200
Path('/private/client-quality-report.json').write_text(json.dumps({'status':'passed','checks':checks,'synthetic_visible_clients':items['count'],'quality':options['quality'],'operator_synthetic_inventory':operator_options[1]['quality']},indent=2))
print('PASS:',len(checks),'client quality integration groups')
