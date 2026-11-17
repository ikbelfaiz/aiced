"""Real dependency outages and Commercial restart, isolated Docker test project."""
import json
import subprocess
import sys
import time
from datetime import datetime,timezone
from compose_context import ROOT,PRIVATE,COMPOSE,URL,TEST
if not TEST:raise SystemExit('Use --test; only the isolated test project may be stopped.')
sys.path[:0]=[str(ROOT/'.tools/python'),str(ROOT/'backend'),str(ROOT/'scripts')]
from s3_rehearsal import Browser
cfg=json.loads((PRIVATE/'config.json').read_text())
def run(*args):subprocess.run([*COMPOSE,*args],cwd=ROOT,check=True,capture_output=True)
b=Browser(URL);b.login('synthetic.operator.a',cfg['admin']['AICED_SEED_PASSWORD'])
url='/api/opportunities/?search=SYNTHETIQUE%20PIPELINE'
status,before,_=b.request(url)
assert status==200 and before['count']>0,'Run pipeline browser fixture first'
checks=[];failures=[]
since=datetime.now(timezone.utc).isoformat()
def recover():
    until=time.monotonic()+45
    while time.monotonic()<until:
        status,data,_=b.request(url)
        if status==200:
            assert data==before
            return
        time.sleep(1)
    raise AssertionError('Pipeline did not recover')
try:
    for service in ['client','iam','db']:
        run('stop',service)
        tick=time.perf_counter()
        status,data,headers=b.request(url)
        assert status in [403,502,503,504] and 'results' not in data and 'statuses' not in data,(service,status)
        failures.append({'dependency':service,'path':url,'status':status,'body':data,
                         'request_id':headers.get('X-Request-ID'),'seconds':time.perf_counter()-tick})
        run('start',service);recover()
        checks.append(service+' stopped: no pipeline rows/counts; same session and identical payload after recovery')
    run('restart','--no-deps','commercial');recover()
    checks.append('Commercial container restart preserves pipeline rows/versions/counts/session')
    (PRIVATE/'pipeline-recovery-report.json').write_text(json.dumps({'status':'passed','checks':checks,'failure_requests':failures},indent=2))
    print('PASS: Client/IAM/PostgreSQL real outage fail-closed, recovery and Commercial restart')
finally:
    run('start','db','client','iam','commercial')
    for service in ['gateway','commercial','client','iam','db']:
        evidence=subprocess.run([*COMPOSE,'logs','--since',since,'--no-color',service],cwd=ROOT,capture_output=True)
        (PRIVATE/('s161-recovery-'+service+'.log')).write_bytes(evidence.stdout+evidence.stderr)
