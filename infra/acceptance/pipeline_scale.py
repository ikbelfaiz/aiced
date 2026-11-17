"""Disposable-only synthetic benchmark. Never prints credentials or client records."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import UUID, uuid5

sys.path[:0] = ['/app', '/scripts']
cfg = json.loads(Path('/private/config.json').read_text())


def worker():
    os.environ.update(cfg['commercial'], DJANGO_SETTINGS_MODULE='commercial_service.settings')
    os.environ['SSL_CERT_FILE'] = '/private/tls/ca.pem'
    import django
    django.setup()
    import resource
    import tracemalloc
    from unittest.mock import patch
    from django.db import connection
    from rest_framework.test import APIRequestFactory
    from commercial_service.pipeline import PipelineView
    from internal_api.client import InternalClient
    counts = {'sql': 0, 'cursor_fetches': 0, 'internal_http': 0}
    post = InternalClient.post
    def http(self, *args, **kwargs):
        counts['internal_http'] += 1
        return post(self, *args, **kwargs)
    def sql(execute, query, params, many, context):
        counts['sql'] += 1
        return execute(query, params, many, context)
    chunked_cursor=connection.chunked_cursor
    class FetchMeter:
        def __init__(self,cursor):self.cursor=cursor
        def __getattr__(self,name):return getattr(self.cursor,name)
        def __enter__(self):return self
        def __exit__(self,*args):self.cursor.close()
        def fetchmany(self,*args):
            counts['cursor_fetches']+=1
            return self.cursor.fetchmany(*args)
    request = APIRequestFactory().get('/api/opportunities/?search=S13-SYNTHETIC&ordering=title&page_size=50', HTTP_HOST='gateway:8080')
    request.COOKIES = json.loads(Path('/private/scale-cookie.json').read_text())
    tracemalloc.start()
    started = time.perf_counter()
    with connection.execute_wrapper(sql), patch.object(InternalClient, 'post', http), patch.object(connection,'chunked_cursor',side_effect=lambda:FetchMeter(chunked_cursor())):
        response = PipelineView.as_view()(request)
        response.render()
    elapsed = time.perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1]
    print(json.dumps(dict(counts, seconds=elapsed, python_peak_bytes=peak,
                         process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                         status=response.status_code, count=response.data.get('count'))))
    return


def main():
    import psycopg
    from s3_rehearsal import Browser
    env = cfg['admin']
    assert env['POSTGRES_DB'] == 'aiced_s7_disposable'
    c = psycopg.connect(host='db', dbname=env['POSTGRES_DB'], user=env['POSTGRES_USER'], password=env['POSTGRES_PASSWORD'], autocommit=True)
    assert c.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()[0] == 'aiced-s7-synthetic-only'
    member, org, actor = c.execute("SELECT m.id,m.organization_id,m.user_id FROM aiced_iam.identity_membership m JOIN aiced_iam.identity_user u ON u.id=m.user_id WHERE u.username='synthetic.reader.b'").fetchone()
    namespace = UUID('916da02f-e102-471a-9863-9098871dfde3')
    role, assignment = [uuid5(namespace, v) for v in ['role', 'assignment']]
    with c.transaction():
        c.execute("INSERT INTO aiced_iam.identity_role(id,code,name,is_active) VALUES(%s,'s13-benchmark','S13 SYNTHETIC ONLY',true) ON CONFLICT DO NOTHING", [role])
        c.execute("INSERT INTO aiced_iam.identity_role_permissions(role_id,capability_id) VALUES(%s,'opportunities.view') ON CONFLICT DO NOTHING", [role])
        c.execute("INSERT INTO aiced_iam.identity_roleassignment(id,membership_id,role_id,scope,is_active,created_at) VALUES(%s,%s,%s,'organization',true,now()) ON CONFLICT(id) DO UPDATE SET is_active=true", [assignment, member, role])
        c.execute("INSERT INTO aiced_commercial.commercial_store_actorref(id,username) VALUES(%s,'synthetic.reader.b') ON CONFLICT DO NOTHING", [actor])
    browser = Browser('http://gateway:8080')
    browser.login('synthetic.reader.b', env['AICED_SEED_PASSWORD'])
    Path('/private/scale-cookie.json').write_text(json.dumps({v.name:v.value for v in browser.jar}))
    report = {'label':sys.argv[1], 'scope':'Commercial SQL and outbound HTTP only; isolated worker tracemalloc/RSS; gateway latency separately', 'datasets':[]}
    runtime = cfg['commercial']
    with psycopg.connect(host='db', dbname=runtime['POSTGRES_DB'], user=runtime['POSTGRES_USER'], password=runtime['POSTGRES_PASSWORD']) as restricted:
        report['runtime_temp_privilege'] = restricted.execute('SELECT has_database_privilege(current_user,current_database(),\'TEMP\')').fetchone()[0]
    for size in [100,500,1000,5000,10000]:
        with c.transaction():
            c.execute("DELETE FROM aiced_commercial.clients_opportunity WHERE notes='S13-SYNTHETIC-BENCHMARK'")
            for start in range(0,size,100):
                parties = [(uuid5(namespace,'party-'+str(i)),org,'S13-SYNTHETIC '+str(i),member) for i in range(start,min(start+100,size))]
                with c.cursor() as cursor:
                    cursor.executemany("INSERT INTO public.clients_party(id,organization_id,kind,display_name,assigned_to_id,created_at,origin,version) VALUES(%s,%s,'physical',%s,%s,now(),'SYNTHETIC_ONLY',1) ON CONFLICT DO NOTHING",parties)
                    cursor.executemany("INSERT INTO public.clients_physicalperson(party_id,first_name,last_name) VALUES(%s,'S13','SYNTHETIC') ON CONFLICT DO NOTHING",[(p[0],) for p in parties])
                    cursor.executemany("INSERT INTO public.clients_crmprofile(party_id,notes,updated_at,email,phone,profession,sector,version) VALUES(%s,'S13 SYNTHETIC ONLY',now(),'','','','',1) ON CONFLICT DO NOTHING",[(p[0],) for p in parties])
                    cursor.executemany('INSERT INTO aiced_commercial.commercial_store_partyref(id,organization_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',[(p[0],org) for p in parties])
                    cursor.executemany("INSERT INTO aiced_commercial.clients_opportunity(id,party_id,title,notes,amount,currency,status,due_date,author_id,version,updated_at) VALUES(%s,%s,%s,'S13-SYNTHETIC-BENCHMARK',NULL,'TND',%s,NULL,%s,1,'2030-01-01T00:00:00Z')",[(uuid5(namespace,'opp-'+str(i)),p[0],f'S13-SYNTHETIC {i:05d}', ['open','won','lost'][i%3],actor) for i,p in enumerate(parties,start)])
        total = c.execute('SELECT count(*),count(distinct party_id) FROM aiced_commercial.clients_opportunity').fetchone()
        probe = subprocess.run([sys.executable,__file__,'--worker'],capture_output=True,text=True)
        if probe.returncode: raise RuntimeError(probe.stderr[-3000:])
        sample = json.loads(probe.stdout.strip().splitlines()[-1])
        latencies=[]
        for _ in range(3):
            started=time.perf_counter()
            status,data,_=browser.request('/api/opportunities/?search=S13-SYNTHETIC&ordering=title&page_size=50')
            latencies.append(round(time.perf_counter()-started,4))
            assert status==sample['status'],(status,sample)
            if status==200:
                assert data['count']==size and sum(data['statuses'].values())==size
                assert len(data['results'])==50
                assert all(row['title'].startswith('S13-SYNTHETIC') for row in data['results'])
        sample.update(size=size,total_opportunities=total[0],distinct_dossiers=total[1],gateway_seconds=latencies)
        report['datasets'].append(sample)
        Path('/private/pipeline-scale-'+sys.argv[1]+'.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(sample),flush=True)
    c.close()


if __name__=='__main__':
    worker() if '--worker' in sys.argv else main()
