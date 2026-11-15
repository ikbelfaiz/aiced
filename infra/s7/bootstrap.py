"""Offline initialization of the dedicated, empty S7 Docker database only."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import uuid

sys.path[:0] = ['/app', '/scripts']
import psycopg
from psycopg import sql
import s3_database as integration
import s4_transfer
import s5_database as iam
import s6_database as commercial

private = Path('/private')
config = json.loads((private / 'config.json').read_text())
admin = config['admin']
assert admin['POSTGRES_HOST'] == 'db' and admin['POSTGRES_DB'] == 'aiced_s7_disposable'
def connect():
    return psycopg.connect(host='db', dbname=admin['POSTGRES_DB'], user=admin['POSTGRES_USER'],
                          password=admin['POSTGRES_PASSWORD'], autocommit=True)

def run(settings, *args, extra=None):
    env = dict(os.environ, **admin, DJANGO_SETTINGS_MODULE=settings,
               AICED_INTERNAL_KEYS=json.dumps(config['keys']))
    service = {'integration_service.settings':'integration','iam_service.settings':'iam',
               'commercial_service.settings':'commercial'}.get(settings)
    if service:
        env['AICED_INTERNAL_KEYS'] = config[service]['AICED_INTERNAL_KEYS']
    env.update(extra or {})
    subprocess.run([sys.executable, '/app/manage.py', *args], env=env, check=True)

def guard(conn, env):
    assert env['POSTGRES_HOST'] == 'db' and conn.execute('SELECT current_database()').fetchone()[0] == 'aiced_s7_disposable'
    assert conn.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()[0] == 'aiced-s7-synthetic-only'

with connect() as c:
    if c.execute("SELECT to_regclass('public.s7_initialized')").fetchone()[0]:
        assert (private / 'initialized').exists(), 'Database/configuration mismatch'
        print('Existing initialized synthetic database retained; no migrations or seeds repeated.')
        sys.exit(0)
    if c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]:
        raise RuntimeError('Nonempty or partially initialized database: refusing automatic repair')
    c.execute("COMMENT ON DATABASE aiced_s7_disposable IS 'aiced-s7-synthetic-only'")

tls = private / 'tls'
def openssl(*args):
    subprocess.run(['openssl', *map(str,args)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
openssl('req','-x509','-newkey','rsa:2048','-nodes','-days','30','-subj','/CN=AICED S7 disposable CA',
        '-keyout',tls/'ca-key.pem','-out',tls/'ca.pem')
for name in ['iam','client','integration','commercial']:
    (tls/name).mkdir(exist_ok=True)
    ext = tls / (name+'.ext')
    ext.write_text('subjectAltName=DNS:'+name+'\nextendedKeyUsage=serverAuth\n')
    openssl('req','-newkey','rsa:2048','-nodes','-subj','/CN='+name,'-keyout',tls/(name+'-key.pem'),'-out',tls/(name+'.csr'))
    openssl('x509','-req','-in',tls/(name+'.csr'),'-CA',tls/'ca.pem','-CAkey',tls/'ca-key.pem',
            '-CAcreateserial','-days','30','-extfile',ext,'-out',tls/(name+'.pem'))
    for filename in ['ca.pem',name+'.pem',name+'-key.pem']:
        shutil.copyfile(tls/filename,tls/name/filename)

# Historical migrations are applied offline, never served as a monolith.
run('config.settings','migrate','--noinput')
for seed in ['seed_synthetic','seed_workspace','seed_prospects']:
    run('config.settings',seed,'--confirm-synthetic')
run('iam_consumer.settings','migrate','iam_consumer','--noinput',extra={'AICED_CONSUMER_MIGRATION':'1'})
env = dict(admin, AICED_REHEARSAL_RUN=uuid.uuid4().hex)
with connect() as c:
    specs = {name:module.provision(c,env,verify=guard) for name,module in
             [('integration',integration),('iam',iam),('commercial',commercial)]}
for name, settings in [('integration','integration_service.settings'),('iam','iam_service.settings'),('commercial','commercial_service.settings')]:
    spec = specs[name]
    run(settings,'migrate','--noinput',extra={'POSTGRES_USER':spec['roles']['migrator'],
        'POSTGRES_PASSWORD':spec['passwords']['migrator'], 'AICED_MIGRATION_ROLE':spec['roles']['owner']})
with connect() as c:
    iam.refs(c)
    # Only newly created metadata in this empty synthetic IAM schema is replaced.
    c.execute(sql.SQL('TRUNCATE {} CASCADE').format(sql.SQL(',').join(sql.Identifier('aiced_iam',t) for t in iam.BASE)))
    iam.transfer(c,'forward')
run('iam_consumer.settings','migrate','--noinput',extra={'AICED_CONSUMER_MIGRATION':'1'})
with connect() as c:
    iam.grants(c,specs['iam'])
    iam.fence(c,specs['iam'],admin['POSTGRES_USER'])
    iam.activate(c,'service')
    integration.grant_runtime(c,specs['integration'])
    s4_transfer.activate(c,'aiced_integration')
    commercial.grants(c,specs['commercial'])
    commercial.transfer(c,'forward')
    commercial.fence(c,specs['commercial'],specs['iam']['roles']['consumer'],True)
    commercial.activate(c,'service')
    # Use the configured stable runtime names, retaining migration/owner identities.
    for name, spec, kind, schema in [
        ('iam',specs['iam'],'runtime','aiced_iam'),
        ('client',specs['iam'],'consumer','public'),
        ('integration',specs['integration'],'runtime','aiced_integration'),
        ('commercial',specs['commercial'],'runtime','aiced_commercial')]:
        role = config[name]['POSTGRES_USER']
        c.execute(sql.SQL('ALTER ROLE {} RENAME TO {}').format(sql.Identifier(spec['roles'][kind]),sql.Identifier(role)))
        c.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role),sql.Literal(config[name]['POSTGRES_PASSWORD'])))
        c.execute(sql.SQL('ALTER ROLE {} IN DATABASE aiced_s7_disposable SET search_path TO {},pg_catalog').format(sql.Identifier(role),sql.Identifier(schema)))
    c.execute('CREATE TABLE public.s7_initialized (id integer PRIMARY KEY CHECK(id=1))')
    c.execute('INSERT INTO public.s7_initialized VALUES (1)')
(private/'ownership.json').write_text(json.dumps(specs,indent=2))
(private/'initialized').write_text('synthetic-only\n')
print('S7 synthetic initialization completed; independent schema histories and restricted runtime roles installed.')
