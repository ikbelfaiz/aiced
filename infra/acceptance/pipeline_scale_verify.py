"""Large synthetic oracle, live permission changes, and in-flight barrier races."""
import json
import os
from pathlib import Path
import sys
from uuid import UUID,uuid5
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time
sys.path[:0]=['/app','/scripts']
import psycopg
from s3_rehearsal import Browser
cfg=json.loads(Path('/private/config.json').read_text())
admin=cfg['admin']
assert admin['POSTGRES_DB']=='aiced_s7_disposable'
def db():return psycopg.connect(host='db',dbname=admin['POSTGRES_DB'],user=admin['POSTGRES_USER'],password=admin['POSTGRES_PASSWORD'],autocommit=True)
with db() as c:
    assert c.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()[0]=='aiced-s7-synthetic-only'
namespace=UUID('916da02f-e102-471a-9863-9098871dfde3')
assignment=uuid5(namespace,'assignment')
b=Browser('http://gateway:8080');b.login('synthetic.reader.b',admin['AICED_SEED_PASSWORD'])
checks=[];race_seconds={}
base={'search':'S13-SYNTHETIC','ordering':'title','page_size':50}
def request(**params):return b.request('/api/opportunities/?'+urlencode({**base,**params}))
for page in [1,2,100,200]:
    status,data,_=request(page=page)
    assert status==200 and data['count']==10000,(status,data)
    expected=[str(uuid5(namespace,'opp-'+str(i))) for i in range((page-1)*50,page*50)]
    assert [r['id'] for r in data['results']]==expected
    assert data['statuses']=={'open':3334,'won':3333,'lost':3333}
checks.append('10000 authorized rows: exact first/second/middle/last pages and all status counts')
status,data,_=request(status='won',ordering='-title',page=67)
expected=list(reversed([i for i in range(10000) if i%3==1]))[3300:3350]
assert status==200 and data['count']==3333 and [r['id'] for r in data['results']]==[str(uuid5(namespace,'opp-'+str(i))) for i in expected]
assert data['statuses']=={'open':3334,'won':3333,'lost':3333}
checks.append('Combined search/status/reverse order/deep pagination preserves pre-status summaries')
stable=sorted(str(uuid5(namespace,'opp-'+str(i))) for i in range(10000))
for ordering in ['due_date','-due_date','-updated_at']:
    status,data,_=request(ordering=ordering)
    assert status==200 and [r['id'] for r in data['results']]==stable[:50]
checks.append('Null due dates and tied timestamps use deterministic UUID tie-breaks for every supported ordering family')
with db() as c:
    party=uuid5(namespace,'party-0')
    c.execute("UPDATE public.clients_party SET display_name='S13 STRASSE NAME ONLY' WHERE id=%s",[party])
try:
    status,data,_=request(search='strasse name only')
    assert status==200 and data['count']==1 and data['results'][0]['id']==str(uuid5(namespace,'opp-0'))
finally:
    with db() as c:c.execute("UPDATE public.clients_party SET display_name='S13-SYNTHETIC 0' WHERE id=%s",[party])
checks.append('Name-only search uses authorized Client metadata rather than Commercial title matching')
with db() as c:c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=false WHERE id=%s',[assignment])
try:
    status,data,_=request()
    assert status==403 and 'results' not in data and 'statuses' not in data
finally:
    with db() as c:c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=true WHERE id=%s',[assignment])
checks.append('Same live session denied immediately after actual permission revocation; no rows/counts')
os.environ.update(cfg['commercial'],DJANGO_SETTINGS_MODULE='commercial_service.settings',SSL_CERT_FILE='/private/tls/ca.pem')
import django
django.setup()
from unittest.mock import patch
from django.db import connection,close_old_connections
from rest_framework.test import APIRequestFactory
from commercial_service.pipeline import PipelineView
from internal_api.client import InternalClient
original=InternalClient.post
cookies={c.name:c.value for c in b.jar}

def run_view(**params):
    close_old_connections()
    req=APIRequestFactory().get('/api/opportunities/?'+urlencode({**base,**params}),HTTP_HOST='gateway:8080')
    req.COOKIES=cookies
    try:return PipelineView.as_view()(req)
    finally:connection.close()

# Pause only after a real Client response. No fabricated permission decisions.
for kind,key in [('IAM',4711239301896721),('Client',591445740000006)]:
    reached=Event();release=Event();waiting=Event();writer_acquired=Event()
    calls=[0]
    def pause(self,path,payload):
        data=original(self,path,payload)
        if path.endswith('opportunity-scope-batch') and payload['party_ids']:
            calls[0]+=1
            if calls[0]==1:
                reached.set()
                assert release.wait(4)
        return data
    def writer():
        with db() as c:
            with c.transaction():
                c.execute("SET LOCAL lock_timeout='5s'")
                waiting.set();started=time.monotonic()
                c.execute('SELECT pg_advisory_xact_lock(%s)',[key])
                writer_acquired.set()
                race_seconds[kind]=round(time.monotonic()-started,4)
                assert race_seconds[kind]<5
                if kind=='IAM':c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=false WHERE id=%s',[assignment])
                else:c.execute('UPDATE public.clients_party SET assigned_to_id=NULL WHERE id=%s',[party])
    try:
        with patch.object(InternalClient,'post',pause),ThreadPoolExecutor(max_workers=2) as pool:
            reader=pool.submit(run_view)
            assert reached.wait(4)
            write=pool.submit(writer);assert waiting.wait(2)
            time.sleep(.15)
            assert not writer_acquired.is_set(),'Scope mutation overtook admitted read'
            release.set();response=reader.result(timeout=15);write.result(timeout=15)
        assert response.status_code==200 and response.data['count']==10000
        assert writer_acquired.is_set()
        if kind=='IAM':assert request()[0]==403
        else:assert request()[1]['count']==9999
    finally:
        release.set()
        with db() as c:
            c.execute('UPDATE aiced_iam.identity_roleassignment SET is_active=true WHERE id=%s',[assignment])
            c.execute("UPDATE public.clients_party SET assigned_to_id=(SELECT m.id FROM aiced_iam.identity_membership m JOIN aiced_iam.identity_user u ON u.id=m.user_id WHERE u.username='synthetic.reader.b') WHERE id=%s",[party])
    checks.append(kind+' exclusive mutation queues behind admitted large read; subsequent request sees committed permission change')

for key in [4711239301896721,591445740000006]:
    with db() as c:
        with c.transaction():
            c.execute('SELECT pg_advisory_xact_lock(%s)',[key])
            status,data,_=request()
            assert status==503 and 'results' not in data and 'statuses' not in data
    assert request()[0]==200
checks.append('New readers fail closed while either exclusive mutation barrier is held; recover after release')

# A late-row Commercial update may commit without waiting for a read. The
# cursor must retain one opportunity snapshot, then the next request sees v2.
role=uuid5(namespace,'role')
with db() as c:c.execute("INSERT INTO aiced_iam.identity_role_permissions(role_id,capability_id) VALUES(%s,'opportunities.manage') ON CONFLICT DO NOTHING",[role])
last=uuid5(namespace,'opp-9999');last_party=uuid5(namespace,'party-9999')
with db() as c:
    journals_before=c.execute("SELECT count(*) FROM aiced_commercial.commercial_store_journal WHERE target_id=%s AND action='clients.opportunities_saved'",[last]).fetchone()[0]
    initial_version=c.execute('SELECT version FROM aiced_commercial.clients_opportunity WHERE id=%s',[last]).fetchone()[0]
url=f'/api/clients/{last_party}/opportunities/{last}/'
reached=Event();release=Event();calls=[0]
try:
    with patch.object(InternalClient,'post',pause),ThreadPoolExecutor(max_workers=1) as pool:
        reader=pool.submit(run_view,page=200)
        assert reached.wait(4)
        status,item,_=b.request(url,{'version':initial_version,'status':'won'},'PATCH')
        assert status==200,(status,item)
        release.set();response=reader.result(timeout=15)
    assert response.status_code==200
    row=response.data['results'][-1]
    assert row['id']==str(last) and row['version']==initial_version and row['status']=='open'
    current=request(page=200)[1]['results'][-1]
    assert current['id']==str(last) and current['version']==initial_version+1 and current['status']=='won'
    assert b.request(url,{'version':initial_version,'status':'lost'},'PATCH')[0]==409
    assert b.request(url,{'version':initial_version+1,'status':'open'},'PATCH')[0]==200
    with db() as c:
        assert c.execute("SELECT count(*) FROM aiced_commercial.commercial_store_journal j JOIN aiced_commercial.commercial_store_outbox o ON o.event_id=j.id WHERE j.target_id=%s AND j.action='clients.opportunities_saved'",[last]).fetchone()[0]==journals_before+2
finally:
    release.set()
    with db() as c:c.execute("DELETE FROM aiced_iam.identity_role_permissions WHERE role_id=%s AND capability_id='opportunities.manage'",[role])
checks.append('Concurrent authorized PATCH retains read snapshot; next request sees update; stale 409 and exact audit/outbox pairs')

with db() as c:c.execute("UPDATE aiced_iam.identity_roleassignment SET expires_at=now()+interval '1 second' WHERE id=%s",[assignment])
try:
    calls=[0]
    def expire(self,path,payload):
        data=original(self,path,payload)
        if path.endswith('opportunity-scope-batch'):
            calls[0]+=1
            if calls[0]==1:time.sleep(1.1)
        return data
    with patch.object(InternalClient,'post',expire):response=run_view()
    assert response.status_code in [403,503] and 'results' not in response.data and 'statuses' not in response.data
finally:
    with db() as c:c.execute('UPDATE aiced_iam.identity_roleassignment SET expires_at=NULL WHERE id=%s',[assignment])
checks.append('Permission expiry during large read fails closed without partial counts or page')

def timeout(self,path,payload):
    from internal_api.client import ServiceUnavailable
    if path.endswith('opportunity-scope-batch') and payload['party_ids']:
        self.timeout=.0001
    return original(self,path,payload)
with patch.object(InternalClient,'post',timeout):
    response=run_view()
    assert response.status_code==503 and 'results' not in response.data
checks.append('Internal timeout after capability admission yields no partial response')

# Exercise signature path binding and persistent replay rejection over actual TLS.
import ssl
import http.client
from internal_api.security import signed_headers
from django.conf import settings
path='/internal/v1/clients/opportunity-scope-batch'
payload={'credentials':{'session_key':cookies['sessionid'],'method':'GET','host':'gateway:8080','scheme':'http'},'party_ids':[str(party)],'search':'S13'}
body=json.dumps(payload).encode()
key=settings.COMMERCIAL_CLIENT_KEY_ID;secret=settings.AICED_INTERNAL_KEYS[key]['secret']
headers=signed_headers(key,secret,'client',path,body)
def tls(headers):
    connection=http.client.HTTPSConnection('client',8446,timeout=3,context=ssl.create_default_context(cafile='/private/tls/ca.pem'))
    try:
        connection.request('POST',path,body,headers)
        response=connection.getresponse();response.read()
        return response.status
    finally:connection.close()
assert tls(headers)==200
assert tls(headers)==403
for forged,headers in [(True,signed_headers(key,secret,'client',path,body)),(False,signed_headers(key,secret,'client',path.removesuffix('-batch'),body))]:
    if forged:headers['X-Aiced-Signature']='0'*64
    assert tls(headers)==403
checks.append('Actual TLS compact route rejects replay, invalid signature and signature for a different path')
Path('/private/pipeline-scale-verification.json').write_text(json.dumps({'status':'passed','checks':checks,'exclusive_writer_wait_seconds':race_seconds},indent=2))
print('PASS: '+str(len(checks))+' large synthetic oracle/permission/concurrency/failure checks')
