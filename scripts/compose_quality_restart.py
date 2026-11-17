"""Quality persistence across an actual disposable PostgreSQL restart."""
import json,subprocess,sys,time
from compose_context import ROOT,PRIVATE,COMPOSE,URL,TEST
if not TEST:raise SystemExit('Use --test; disposable stack only.')
sys.path[:0]=[str(ROOT/'.tools/python'),str(ROOT/'backend'),str(ROOT/'scripts')]
from s3_rehearsal import Browser
cfg=json.loads((PRIVATE/'config.json').read_text())
def run(*args):return subprocess.run([*COMPOSE,*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
b=Browser(URL);b.login('synthetic.operator.a',cfg['admin']['AICED_SEED_PASSWORD'])
items=b.request('/api/clients/?ordering=display_name&completeness_min=0&page_size=8')[1]
ident=items['results'][0]['id']
paths=['/api/clients/filter-options/',f'/api/clients/{ident}/quality/','/api/clients/?ordering=display_name&completeness_min=0&page_size=8']
before={p:b.request(p)[1] for p in paths}
run('restart','--no-deps','db')
deadline=time.monotonic()+60
while time.monotonic()<deadline:
    try:
        responses={p:b.request(p) for p in paths}
        if all(r[0]==200 for r in responses.values()):
            assert {p:r[1] for p,r in responses.items()}==before
            break
    except (OSError,TimeoutError):pass
    time.sleep(1)
else:raise AssertionError('Database recovery did not preserve quality/list/options')
(PRIVATE/'quality-restart-report.json').write_text(json.dumps({'status':'passed','checks':['Actual PostgreSQL restart: same authenticated session, identical client page, scoped options, diagnostics and profile quality']},indent=2))
print('PASS: database restart preserves Client segmentation and quality')
