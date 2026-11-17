"""Create private configuration for a fresh Docker-only synthetic S7 stack."""
import json
import secrets
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from compose_context import PRIVATE
dest = PRIVATE
if (dest / 'config.json').exists():
    raise SystemExit('Private S7 configuration already exists; refusing to replace credentials.')
dest.mkdir(parents=True, exist_ok=True)
(dest / 'tls').mkdir(exist_ok=True)
for service in ['iam','client','integration','commercial']:
    (dest / 'tls' / service).mkdir(exist_ok=True)
keys = {}
for ident, service, audiences in [
    ('client-iam-v1', 'client_crm', ['iam', 'audit']),
    ('integration-v1', 'integration', ['iam', 'audit']),
    ('client-integration-v1', 'client_crm', ['integration']),
    ('commercial-iam-v1', 'commercial', ['iam', 'audit']),
    ('commercial-client-v1', 'commercial', ['client']),
    ('client-commercial-v1', 'client_crm', ['commercial']),
]:
    keys[ident] = dict(secret=secrets.token_urlsafe(48), service=service, audiences=audiences)
common = dict(POSTGRES_DB='aiced_s7_disposable', POSTGRES_HOST='db', POSTGRES_PORT='5432',
              DJANGO_DEBUG='1', DJANGO_ALLOWED_HOSTS='localhost,127.0.0.1,iam,client,commercial,integration,gateway',
              AICED_GATEWAY_KEY=secrets.token_urlsafe(48), SSL_CERT_FILE='/run/tls/ca.pem',
              LOGIN_ACCOUNT_LIMIT='1000', LOGIN_IP_LIMIT='2000', IMPORT_MAX_DAILY_BATCHES='2000',
              IMPORT_MAX_STAGED_BATCHES='1000')
admin = dict(common, POSTGRES_USER='s7_admin', POSTGRES_PASSWORD=secrets.token_urlsafe(48),
             DJANGO_SECRET_KEY=secrets.token_urlsafe(48), AICED_SEED_PASSWORD=secrets.token_urlsafe(32))
config = dict(admin=admin, keys=keys)
(dest / 'config.json').write_text(json.dumps(config, indent=2))
def envfile(name, data):
    (dest / (name + '.env')).write_text('\n'.join(k+'='+str(v) for k,v in data.items())+'\n')
envfile('db', {k:admin[k] for k in ['POSTGRES_DB','POSTGRES_USER','POSTGRES_PASSWORD']})
envfile('gateway', {'AICED_GATEWAY_KEY': common['AICED_GATEWAY_KEY']})
for name, ids in {
    'iam':['client-iam-v1','integration-v1','commercial-iam-v1'],
    'client':['client-iam-v1','client-integration-v1','client-commercial-v1','commercial-client-v1'],
    'integration':['integration-v1','client-integration-v1'],
    'commercial':['commercial-iam-v1','commercial-client-v1','client-commercial-v1'],
}.items():
    data = dict(common, POSTGRES_USER='s7_'+name, POSTGRES_PASSWORD=secrets.token_urlsafe(48),
                DJANGO_SECRET_KEY=secrets.token_urlsafe(48),
                AICED_INTERNAL_KEYS=json.dumps({k:keys[k] for k in ids}, separators=(',',':')),
                AICED_IAM_URL='https://iam:8443')
    if name == 'client':
        data.update(AICED_COMMERCIAL_REMOTE='1', AICED_COMMERCIAL_URL='https://commercial:8445',
                    AICED_INTEGRATION_AUDIT_URL='https://integration:8444',
                    AICED_INTEGRATION_AUDIT_KEY_ID='client-integration-v1')
    if name == 'commercial': data['AICED_CLIENT_URL']='https://client:8446'
    config[name] = data
    envfile(name, data)
(dest / 'config.json').write_text(json.dumps(config, indent=2))
baseline = ROOT / '.local/migration-baseline/ad738f3cd11047e290efb80b12af1bc2/openapi.yaml'
if baseline.exists():
    shutil.copyfile(baseline, dest / 'openapi-baseline.yaml')
print('Private synthetic configuration generated in '+str(dest.relative_to(ROOT))+' (excluded from Git).')
