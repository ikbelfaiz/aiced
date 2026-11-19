"""Additive Integration-owned migration, guarded disposable Docker database only."""
import json
import os
import subprocess
import sys
from pathlib import Path
import psycopg
from psycopg import sql


def apply(config):
    admin = config['admin']
    assert admin['POSTGRES_HOST'] == 'db' and admin['POSTGRES_DB'] == 'aiced_s7_disposable'
    with psycopg.connect(host='db', dbname=admin['POSTGRES_DB'], user=admin['POSTGRES_USER'], password=admin['POSTGRES_PASSWORD']) as c:
        assert c.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()[0] == 'aiced-s7-synthetic-only'
        owner = c.execute("SELECT tableowner FROM pg_tables WHERE schemaname='aiced_integration' AND tablename='ingestion_importpolicy'").fetchone()[0]
        assert owner and owner != config['integration']['POSTGRES_USER']
    env = {**os.environ, **config['integration'], **{k:v for k,v in admin.items() if k.startswith('POSTGRES_')}, 'DJANGO_SETTINGS_MODULE':'integration_service.settings', 'AICED_MIGRATION_ROLE':owner}
    subprocess.run([sys.executable, '/app/manage.py', 'migrate', 'integration_store', '--noinput'], env=env, check=True)
    with psycopg.connect(host='db', dbname=admin['POSTGRES_DB'], user=admin['POSTGRES_USER'], password=admin['POSTGRES_PASSWORD']) as c:
        c.execute(sql.SQL('GRANT UPDATE (fixed_configuration_version) ON aiced_integration.ingestion_importbatch TO {}').format(sql.Identifier(config['integration']['POSTGRES_USER'])))
    print('Reusable publication rule migration checked under existing Integration owner; history retained, no approvals or classifications backfilled.')


if __name__ == '__main__':
    apply(json.loads(Path('/private/config.json').read_text()))
