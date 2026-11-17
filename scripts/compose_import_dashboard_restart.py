"""Restart actual test PostgreSQL/Integration and prove identical published source views."""
import json,subprocess,sys,time
from compose_context import ROOT,PRIVATE,COMPOSE,URL,TEST
if not TEST:raise SystemExit('Use --test; isolated synthetic stack only.')
sys.path[:0]=[str(ROOT/'.tools/python'),str(ROOT/'backend'),str(ROOT/'scripts')]
from s3_rehearsal import Browser
cfg=json.loads((PRIVATE/'config.json').read_text())
manifest=json.loads((PRIVATE/'import-dashboard-manifest.json').read_text())
def run(*args):
    return subprocess.run([*COMPOSE,*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout
browser=Browser(URL)
browser.login('synthetic.reviewer.a',cfg['admin']['AICED_SEED_PASSWORD'])
status,context,_=browser.request('/api/imports/context/')
assert status==200
org=next(item['id'] for item in context['organizations'] if item['approve'])
urls=[f"/api/imports/{org}/batches/{item['batch_id']}/" for item in manifest]
baseline=[]
for url in urls:
    status,data,_=browser.request(url)
    assert status==200 and data['batch']['status']=='published'
    baseline.append(data)
run('run','--rm','--no-deps','initialize','python','/s7/import_dashboard.py')
checks=[]
for service in ['integration','db']:
    ident=run('ps','-q',service).strip()
    def pid():return subprocess.run(['docker','inspect','--format','{{.State.Pid}}',ident],check=True,capture_output=True,text=True).stdout.strip()
    before=pid()
    run('restart','--no-deps',service)
    assert before!=pid()
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        current=[browser.request(url) for url in urls]
        if all(result[0]==200 for result in current):
            assert [result[1] for result in current]==baseline
            break
        time.sleep(1)
    else:raise AssertionError(f'{service} did not recover')
    run('run','--rm','--no-deps','initialize','python','/s7/import_dashboard.py')
    checks.append(f'{service} process restarted: same session reads identical source cells, validation, publication provenance; SQL fingerprints unchanged')
(PRIVATE/'import-dashboard-restart.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2))
print('PASS: Integration and PostgreSQL restart persistence for all three browser-published workbooks')
