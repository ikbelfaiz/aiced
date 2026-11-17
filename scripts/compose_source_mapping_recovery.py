"""Actual outages/restarts; only disposable synthetic Compose, no source activation."""
import json,subprocess,sys,time
from compose_context import ROOT,PRIVATE,COMPOSE,URL,TEST
if not TEST:raise SystemExit('Use --test; isolated synthetic database only.')
sys.path[:0]=[str(ROOT/'.tools/python'),str(ROOT/'backend'),str(ROOT/'scripts')]
from s3_rehearsal import Browser
cfg=json.loads((PRIVATE/'config.json').read_text())
browser=Browser(URL);browser.login('synthetic.operator.a',cfg['admin']['AICED_SEED_PASSWORD'])
party=browser.request('/api/clients/?page_size=1')[1]['results'][0]['id']
base=f'/api/clients/{party}/source-mapping-preview/'
paths=[base+'?scenario='+case for case in ['unique','ambiguous','missing','duplicate','multiple_accounts','conflicting_identifiers']]
def run(*args):return subprocess.run([*COMPOSE,*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
def payload(path):
    status,data,_=browser.request(path)
    assert status==200,(status,data)
    return data
before={path:payload(path) for path in paths};checks=[]
def recover():
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        try:
            assert {path:payload(path) for path in paths}==before
            return
        except (AssertionError,OSError,TimeoutError):time.sleep(1)
    raise AssertionError('Synthetic preview did not recover identical payloads')
try:
    for service in ['integration','client','iam']:
        run('stop',service)
        try:
            status,data,_=browser.request(paths[0])
            assert status in [403,502,503,504] and not any(key in data for key in ['records','relationships']),(service,status,data)
        finally:run('start',service)
        recover();checks.append(service+' unavailable: no candidates/fallback; identical six-scenario recovery with same session')
    for service in ['integration','client','db']:
        ident=run('ps','-q',service)
        def pid():return subprocess.run(['docker','inspect','--format','{{.State.Pid}}',ident],check=True,capture_output=True,text=True).stdout.strip()
        old=pid();run('restart','--no-deps',service)
        assert pid()!=old
        recover();checks.append(service+' process restart: identical versioned fixture/provenance and no stored relationships')
finally:run('start','iam','client','integration','db')
(PRIVATE/'source-mapping-recovery.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2))
print('PASS:',len(checks),'source mapping actual outage/restart checks')
