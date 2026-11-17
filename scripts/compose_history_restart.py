"""Verify new interaction history persistence after only the test Client restarts."""
import json
from pathlib import Path
import subprocess
import sys
import time
from compose_context import ROOT, PRIVATE, COMPOSE, URL, TEST

if not TEST:
    raise SystemExit('Use --test; this recovery probe is restricted to the isolated test project.')
sys.path[:0]=[str(ROOT/'.tools/python'),str(ROOT/'backend'),str(ROOT/'scripts')]
from s3_rehearsal import Browser
cfg=json.loads((PRIVATE/'config.json').read_text())
def run(*args):
    return subprocess.run([*COMPOSE,*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
def pid(service):
    ident=run('ps','-q',service)
    return subprocess.run(['docker','inspect','--format','{{.State.Pid}}',ident],check=True,capture_output=True,text=True).stdout.strip()
b=Browser(URL)
b.login('synthetic.operator.a',cfg['admin']['AICED_SEED_PASSWORD'])
url='/api/interactions/?search=SYNTHETIQUE%20HISTORIQUE'
status,before,_=b.request(url)
assert status==200 and before['count']>0, 'Run the history browser scenario first'
pids={s:pid(s) for s in ['client','iam','commercial','integration']}
run('restart','--no-deps','client')
until=time.monotonic()+60
while time.monotonic()<until:
    status,after,_=b.request(url)
    if status==200: break
    time.sleep(1)
assert status==200 and after==before
assert pid('client')!=pids['client']
assert all(pid(s)==pids[s] for s in ['iam','commercial','integration'])
report={'status':'passed','checks':['new Client process; three peers unchanged',
    'same session reads identical history rows/count after container restart']}
(PRIVATE/'history-restart-report.json').write_text(json.dumps(report,indent=2))
print('PASS: history rows/count and session persist after isolated Client restart; three peers unchanged')
