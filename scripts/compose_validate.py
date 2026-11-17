"""Validate naming parity and application/test data separation with actual Compose."""
import json
from pathlib import Path
import subprocess
from compose_context import ROOT

RENAMES={
    'compose.yaml':'compose.legacy.yaml',
    'compose.s3.yaml':'compose.integration-candidate.yaml',
    'compose.s4.yaml':'compose.integration-cutover.yaml',
    'compose.s5.yaml':'compose.iam-cutover.yaml',
    'compose.s6.yaml':'compose.commercial-cutover.yaml',
    'compose.direct.yaml':'compose.legacy-direct.yaml',
    'compose.s7.yaml':'compose.yaml', 'compose.s7.dev.yaml':'compose.dev.yaml',
}
def config(files,private=False):
    cmd=['docker','compose','--project-directory',str(ROOT)]
    for f in files: cmd+=['-f',str(f)]
    cmd+=['config','--format','json']
    if not private: cmd+=['--no-env-resolution','--no-interpolate']
    return json.loads(subprocess.run(cmd,cwd=ROOT,check=True,capture_output=True,text=True).stdout)
def portable(value):
    if isinstance(value,dict): return {k:portable(v) for k,v in value.items()}
    if isinstance(value,list): return [portable(v) for v in value]
    if isinstance(value,str): return value.replace(str(ROOT),'${WORKSPACE}').replace('\\','/')
    return value
# Captured from pre-rename Git sources, compared successfully before freezing.
# Contains source configuration only: no resolved env values or private paths.
baseline=json.loads((ROOT/'infra/acceptance/compose-layout-baseline.json').read_text())
for old,new in RENAMES.items():
    base=[] if new in ['compose.yaml','compose.legacy.yaml'] else [ROOT/('compose.yaml' if new=='compose.dev.yaml' else 'compose.legacy.yaml')]
    assert baseline[new]==portable(config(base+[ROOT/new])),new+' changed container configuration'
main=config([ROOT/'compose.yaml'],private=True)
test=config([ROOT/'compose.yaml',ROOT/'compose.test.yaml'],private=True)
assert main['name']!=test['name']
assert main['volumes']['s7_database']['name']!=test['volumes']['s7_database']['name']
for name in ['db','iam','client','commercial','integration','gateway']:
    a=main['services'][name]['environment'];b=test['services'][name]['environment']
    secret='AICED_GATEWAY_KEY' if name=='gateway' else 'POSTGRES_PASSWORD'
    assert a[secret]!=b[secret],name+' shares credentials'
assert main['services']['initialize']['volumes'][0:]!=test['services']['initialize']['volumes'][0:]
assert not main['services']['db'].get('ports') and not test['services']['db'].get('ports')
report={'status':'passed','renamed_configurations':len(RENAMES),'container_behavior_preserved':True,'test_credentials_and_volume_isolated':True}
(ROOT/'.local/s8').mkdir(exist_ok=True)
(ROOT/'.local/s8/compose-validation.json').write_text(json.dumps(report,indent=2))
print('PASS: 8 renamed Compose configurations preserve behavior; test project, volume and credentials differ')
