"""Bounded concurrent real gateway reads; record failures, never retry them."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import subprocess
import sys
import time
from threading import Barrier
from compose_context import ROOT, PRIVATE, COMPOSE, URL, TEST
if not TEST:raise SystemExit('Use --test; synthetic disposable stack only.')
sys.path[:0]=[str(ROOT/'.tools/python'),str(ROOT/'scripts')]
from s3_rehearsal import Browser
cfg=json.loads((PRIVATE/'config.json').read_text())
b=Browser(URL);b.login('synthetic.reader.b',cfg['admin']['AICED_SEED_PASSWORD'])
path='/api/opportunities/?search=S13-SYNTHETIC&ordering=title&page_size=50'
status,expected,_=b.request(path)
assert status==200 and expected['count']==10000,(status,expected)
since=datetime.now(timezone.utc).isoformat()
report=[]
for concurrency in [2,4]:
    barrier=Barrier(concurrency)
    def read(index):
        browser=Browser(URL)
        for cookie in b.jar:browser.jar.set_cookie(copy.copy(cookie))
        barrier.wait(timeout=10)
        tick=time.perf_counter()
        status,data,headers=browser.request(path)
        seconds=time.perf_counter()-tick
        if status==200:assert data==expected
        else:assert status in [403,502,503,504] and 'results' not in data and 'statuses' not in data
        return {'status':status,'seconds':seconds,'request_id':headers.get('X-Request-ID'),
                'response':{'count':data['count']} if status==200 else data}
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        report.append({'concurrency':concurrency,'requests':list(pool.map(read,range(concurrency)))})
for service in ['gateway','commercial','client','iam','db']:
    logs=subprocess.run([*COMPOSE,'logs','--since',since,'--no-color',service],cwd=ROOT,capture_output=True)
    (PRIVATE/('s161-concurrent-'+service+'.log')).write_bytes(logs.stdout+logs.stderr)
(PRIVATE/'s161-concurrency.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
assert all(r['status']==200 for wave in report for r in wave['requests']),'Concurrent capacity regression remains open; see evidence.'
