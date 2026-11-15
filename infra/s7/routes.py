"""Exercise every frozen public method/path through the four-service gateway."""
import json
from pathlib import Path
import re
import sys
sys.path[:0]=['/app','/scripts']
from s3_rehearsal import Browser
baseline=json.loads(Path('/app/contracts/public-api-baseline.json').read_text())
results=[]
for route in baseline['routes']:
    path=re.sub(r'<uuid:[^>]+>','00000000-0000-0000-0000-000000000000',route['path'])
    for method in route['methods']:
        code,_,_=Browser('http://gateway:8080').request(path,{} if method in ['POST','PATCH','DELETE'] else None,method)
        allowed = [200] if path in ['/api/health/','/api/auth/csrf/'] else [400,403] if path=='/api/auth/login/' else [403]
        assert code in allowed,(method,path,code)
        results.append(dict(path=route['path'],method=method,status=code))
assert len(baseline['routes'])==38 and len(results)==47
assert Browser('http://client:8000').request('/api/auth/csrf/')[0]==503
assert Browser('http://client:8000').request('/api/clients/00000000-0000-0000-0000-000000000000/opportunities/')[0]==503
for service,port in [('iam',8003),('integration',8002),('commercial',8004)]:
    assert Browser(f'http://{service}:{port}').request('/api/clients/')[0]==404
Path('/private/routes-report.json').write_text(json.dumps({'status':'passed','routes':38,'method_paths':47,
    'checks':results,'direct_retired_routes_denied':True},indent=2))
print('PASS: all 38 public patterns / 47 method-paths reject unauthenticated operations or serve explicit public contracts; retired routes denied')
