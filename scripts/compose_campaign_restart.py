"""Campaign persistence + actual IAM outage on the isolated Compose stack."""
import json,subprocess,sys,time
from compose_context import ROOT,PRIVATE,COMPOSE,URL,TEST
if not TEST:raise SystemExit('Use --test; isolated synthetic stack only.')
sys.path[:0]=[str(ROOT/'.tools/python'),str(ROOT/'backend'),str(ROOT/'scripts')]
from s3_rehearsal import Browser
cfg=json.loads((PRIVATE/'config.json').read_text())
def run(*args):return subprocess.run([*COMPOSE,*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
def pid(service):
    ident=run('ps','-q',service)
    return subprocess.run(['docker','inspect','--format','{{.State.Pid}}',ident],check=True,capture_output=True,text=True).stdout.strip()
b=Browser(URL);b.login('synthetic.operator.a',cfg['admin']['AICED_SEED_PASSWORD'])
url='/api/campaigns/?search=SYNTHETIQUE%20CAMPAGNE'
status,before,_=b.request(url)
assert status==200 and before['count']>0,'Run campaign browser fixture first'
checks=[]
def recover():
    until=time.monotonic()+60
    while time.monotonic()<until:
        status,after,_=b.request(url)
        if status==200:
            assert after==before
            return
        time.sleep(1)
    raise AssertionError('Campaigns did not recover')
try:
    peers={s:pid(s) for s in ['iam','client','integration']};old=pid('commercial')
    run('restart','--no-deps','commercial');recover()
    assert pid('commercial')!=old and all(pid(s)==p for s,p in peers.items())
    checks.append('Only Commercial process restarted; same session reads identical names/notes/dates/versions/counts')
    run('stop','iam')
    status,data,_=b.request(url)
    assert status in [403,502,503,504] and 'results' not in data and 'count' not in data
    item=before['results'][0]
    status,data,_=b.request('/api/campaigns/'+item['id']+'/',{'version':item['version'],'description':'SYNTHETIC IAM OUTAGE: MUST NOT SAVE'},'PATCH')
    assert status in [403,502,503,504] and 'id' not in data
    run('start','iam');recover()
    checks.append('Actual IAM outage blocks reads and writes; same-session identical payload after IAM recovery')
finally:run('start','iam','commercial')
(PRIVATE/'campaign-restart-report.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2))
print('PASS: campaign restart persistence and actual IAM outage/recovery')
