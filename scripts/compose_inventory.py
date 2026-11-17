"""Capture sanitized live container evidence without printing environments."""
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
from compose_context import PRIVATE, COMPOSE
def run(*args):
    return subprocess.run(['docker',*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
report={'engine':json.loads(run('version','--format','{{json .Server}}'))['Version'],
        'compose':run('compose','version','--short'),'services':{}}
for name in ['db','iam','client','commercial','integration','frontend','gateway']:
    ident=subprocess.run([*COMPOSE,'ps','-q',name],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
    assert ident,name+' missing'
    c=json.loads(run('inspect',ident))[0]
    env=dict(v.split('=',1) for v in c['Config']['Env'])
    ports=c['HostConfig'].get('PortBindings') or {}
    assert name=='gateway' or not ports,(name,'unexpected published port')
    assert c['State']['Health']['Status']=='healthy',name
    item={'command':c['Config']['Cmd'],'status':c['State']['Status'],
          'health':c['State']['Health']['Status'],'image_id':c['Image'],
          'published_ports':ports,'host_pid':c['State']['Pid']}
    if name in ['iam','client','commercial','integration']:
        assert env['POSTGRES_HOST']=='db' and env['POSTGRES_DB']=='aiced_s7_disposable'
        assert env['POSTGRES_USER']=='s7_'+name
        assert not env.get('AICED_MIGRATION_ROLE')
        assert c['Config']['Cmd']==['python','-m',{'iam':'iam_service.serve','client':'iam_consumer.serve',
            'commercial':'commercial_service.serve','integration':'integration_service.serve'}[name]]
        urls={k:v for k,v in env.items() if k.endswith('_URL')}
        assert all('localhost' not in v and '127.0.0.1' not in v and 'host.docker.internal' not in v for v in urls.values())
        item.update(database_host=env['POSTGRES_HOST'],database_user=env['POSTGRES_USER'],peer_urls=urls)
    if name=='gateway':
        assert env['AICED_REQUIRE_SERVICES']=='1'
        item['upstreams']={k:v for k,v in env.items() if k.endswith('_UPSTREAM')}
    report['services'][name]=item
assert len({report['services'][s]['host_pid'] for s in ['iam','client','commercial','integration']})==4
(PRIVATE/'container-inventory.json').write_text(json.dumps(report,indent=2))
print('PASS: seven healthy application containers, four distinct Django processes, internal DNS, own credentials and gateway-only published port')
