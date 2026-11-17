"""One real gateway request: Commercial RSS samples and all internal HTTP hops."""
import json
import subprocess
import sys
import time
from datetime import datetime,timezone
from threading import Event,Thread
from compose_context import ROOT,PRIVATE,COMPOSE,URL,TEST
if not TEST:raise SystemExit('Use --test; S13 synthetic test stack only.')
sys.path[:0]=[str(ROOT/'.tools/python'),str(ROOT/'backend'),str(ROOT/'scripts')]
from s3_rehearsal import Browser
cfg=json.loads((PRIVATE/'config.json').read_text())
b=Browser(URL);b.login('synthetic.reader.b',cfg['admin']['AICED_SEED_PASSWORD'])
stop=Event();rss=[]
def sample():
    while not stop.is_set():
        code="from pathlib import Path; processes=[p for p in Path('/proc').iterdir() if p.name.isdigit() and (p/'comm').read_text().startswith('python') and b'commercial_service.serve' in (p/'cmdline').read_bytes().split(b'\\0')]; assert len(processes)==1; print(next(line.split()[1] for line in (processes[0]/'status').read_text().splitlines() if line.startswith('VmRSS:')))"
        result=subprocess.run([*COMPOSE,'exec','-T','commercial','python','-c',code],cwd=ROOT,capture_output=True,text=True,check=True)
        rss.append(int(result.stdout.strip()))
        stop.wait(.1)
thread=Thread(target=sample);thread.start()
since=datetime.now(timezone.utc).isoformat()
started=time.perf_counter()
try:
    status,data,_=b.request('/api/opportunities/?search=S13-SYNTHETIC&ordering=title&page_size=50')
    seconds=time.perf_counter()-started
finally:
    stop.set();thread.join()
assert status==200 and data['count']==10000,(status,data)
logs=subprocess.run([*COMPOSE,'logs','--since',since,'--no-log-prefix','client','iam'],cwd=ROOT,capture_output=True,text=True,check=True).stdout
scope=sum('"POST /internal/v1/clients/opportunity-scope' in line for line in logs.splitlines())
snapshots=sum('"POST /internal/v1/grants/snapshot ' in line for line in logs.splitlines())
assert scope>=3 and snapshots==scope+2,(scope,snapshots)
report={'status':'passed','gateway_seconds':seconds,'visible_count':data['count'],'commercial_rss_kib_samples':rss,'commercial_to_client_requests':scope,'all_iam_snapshot_requests':snapshots,'total_internal_http':scope+snapshots,'scope':'Single isolated gateway request; process RSS sampled, SQL instrumented separately by pipeline_scale.py'}
(PRIVATE/'pipeline-http-metrics.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
