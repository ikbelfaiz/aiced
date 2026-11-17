"""Explicit Commercial-owned draft migration; marked disposable database only."""
import json,os,subprocess,sys
from pathlib import Path
import psycopg
from psycopg import sql


def apply(config):
    admin=config['admin']
    assert admin['POSTGRES_HOST']=='db' and admin['POSTGRES_DB']=='aiced_s7_disposable'
    def db():return psycopg.connect(host='db',dbname=admin['POSTGRES_DB'],user=admin['POSTGRES_USER'],password=admin['POSTGRES_PASSWORD'],autocommit=True)
    with db() as c:
        assert c.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()[0]=='aiced-s7-synthetic-only'
        owner=c.execute("SELECT tableowner FROM pg_tables WHERE schemaname='aiced_commercial' AND tablename='clients_opportunity'").fetchone()[0]
        assert owner and owner!=config['commercial']['POSTGRES_USER']
    env={**os.environ,**config['commercial'],**{k:v for k,v in admin.items() if k.startswith('POSTGRES_')},'DJANGO_SETTINGS_MODULE':'commercial_service.settings','AICED_MIGRATION_ROLE':owner}
    subprocess.run([sys.executable,'/app/manage.py','migrate','commercial_store','--noinput'],env=env,check=True)
    with db() as c:
        with c.transaction():
            actual=c.execute("SELECT tableowner FROM pg_tables WHERE schemaname='aiced_commercial' AND tablename='commercial_store_campaigndraft'").fetchone()[0]
            assert actual==owner
            c.execute('REVOKE ALL ON aiced_commercial.commercial_store_campaigndraft FROM PUBLIC')
            c.execute(sql.SQL('REVOKE ALL ON aiced_commercial.commercial_store_campaigndraft FROM {}').format(sql.Identifier(config['commercial']['POSTGRES_USER'])))
            c.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON aiced_commercial.commercial_store_campaigndraft TO {}').format(sql.Identifier(config['commercial']['POSTGRES_USER'])))
    print('Commercial draft migration applied under existing owner; runtime SELECT/INSERT/UPDATE only.')


if __name__=='__main__':apply(json.loads(Path('/private/config.json').read_text()))
