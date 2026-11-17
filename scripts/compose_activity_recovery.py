"""Actual service outages and report recovery; isolated synthetic Compose only."""
import json,subprocess,sys,time
from compose_context import ROOT,PRIVATE,COMPOSE,URL,TEST
if not TEST:raise SystemExit('Use --test; isolated synthetic database only.')
sys.path[:0]=[str(ROOT/'.tools/python'),str(ROOT/'backend'),str(ROOT/'scripts')]
from s3_rehearsal import Browser
cfg=json.loads((PRIVATE/'config.json').read_text())
b=Browser(URL);b.login('synthetic.operator.a',cfg['admin']['AICED_SEED_PASSWORD'])
report='/api/clients/activity-report/?date_from=2024-05-17&date_to=2024-05-17'
paths=[report,'/api/opportunities/?page_size=1','/api/campaigns/?page_size=1']
checks=[]
def run(*args):return subprocess.run([*COMPOSE,*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
def payload(path):
    status,data,_=b.request(path);assert status==200,(path,status,data)
    return {key:value for key,value in data.items() if key!='generated_at'}
before={p:payload(p) for p in paths}
def recover():
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        try:
            after={p:payload(p) for p in paths}
            assert after==before
            return
        except (AssertionError,OSError,TimeoutError):time.sleep(1)
    raise AssertionError('Reports did not recover identical authorized counts/series/stock')
try:
    for service,failed,remaining in [
        ('client',[report,paths[1]],[paths[2]]),
        ('commercial',paths[1:],[report]),
        ('iam',paths,[]),
    ]:
        run('stop',service)
        try:
            for path in failed:
                status,data,_=b.request(path)
                assert status in [403,502,503,504] and not any(k in data for k in ['count','statuses','interactions','appointments','followups','results']),(service,path,status,data)
            for path in remaining:assert payload(path)==before[path]
        finally:run('start',service)
        recover();checks.append(service+' outage: protected statistics unavailable, independent owner remains available, identical recovery with existing session')
    run('restart','--no-deps','db');recover()
    checks.append('Actual PostgreSQL restart preserves report series and all owner-specific stock counts')
finally:run('start','iam','client','commercial','db')
(PRIVATE/'activity-recovery-report.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2))
print('PASS:',len(checks),'report outage/recovery checks')
