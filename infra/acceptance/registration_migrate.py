"""Apply the IAM registration table to the marked synthetic Compose database."""
import os
import subprocess
import sys

import psycopg
from psycopg import sql


def apply(config):
    admin = config['admin']
    assert admin['POSTGRES_HOST'] == 'db' and admin['POSTGRES_DB'] == 'aiced_s7_disposable'
    with psycopg.connect(host='db', dbname=admin['POSTGRES_DB'], user=admin['POSTGRES_USER'], password=admin['POSTGRES_PASSWORD'], autocommit=True) as conn:
        assert conn.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()[0] == 'aiced-s7-synthetic-only'
        owner = conn.execute("SELECT tableowner FROM pg_tables WHERE schemaname='aiced_iam' AND tablename='identity_user'").fetchone()[0]
        env = {**os.environ, **admin, 'DJANGO_SETTINGS_MODULE': 'iam_service.settings', 'AICED_MIGRATION_ROLE': owner}
        subprocess.run([sys.executable, '/app/manage.py', 'migrate', 'identity', '--noinput'], env=env, check=True)
        with conn.transaction():
            conn.execute('REVOKE ALL ON aiced_iam.identity_registrationrequest FROM PUBLIC')
            conn.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON aiced_iam.identity_registrationrequest TO {}').format(sql.Identifier(config['iam']['POSTGRES_USER'])))
    print('IAM account-request migration applied; runtime access remains IAM-only.')
