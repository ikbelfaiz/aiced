"""Existing regression suites in a container, on a separate disposable test DB."""
import json
import os
from pathlib import Path
import subprocess
import sys

cfg=json.loads(Path('/private/config.json').read_text())
results=[]
for name,settings,labels in [
    ('regression','config.settings',['core','identity','clients','ingestion','audit','internal_api','contracts','service_architecture','gateway_tests']),
    ('iam','iam_service.settings',['iam_service']),
    ('integration','integration_service.settings',['integration_store']),
    ('commercial','commercial_service.settings',['commercial_service']),
]:
    env=dict(os.environ,**cfg['admin' if name=='regression' else name],DJANGO_SETTINGS_MODULE=settings)
    if name=='regression':
        env['AICED_INTERNAL_KEYS']=json.dumps(cfg['keys'])
        env.pop('AICED_GATEWAY_KEY',None)
        for key in ['LOGIN_ACCOUNT_LIMIT','LOGIN_IP_LIMIT','IMPORT_MAX_DAILY_BATCHES','IMPORT_MAX_STAGED_BATCHES']:
            env.pop(key,None)
    with open('/private/'+name+'-tests.log','w') as log:
        p=subprocess.run([sys.executable,'/app/manage.py','test',*labels,'--noinput'],env=env,stdout=log,stderr=log)
    results.append(dict(suite=name,exit_code=p.returncode))
    print(name+': exit '+str(p.returncode),flush=True)
Path('/private/regression-report.json').write_text(json.dumps(results,indent=2))
sys.exit(int(any(r['exit_code'] for r in results)))
