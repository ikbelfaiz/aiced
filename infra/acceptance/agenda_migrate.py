"""Explicit Client-owned agenda migration on the marked disposable DB only."""
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
        # Do not create a hidden parallel ownership graph; verify existing owner.
        owner=c.execute("SELECT tableowner FROM pg_tables WHERE schemaname='public' AND tablename='clients_interaction'").fetchone()[0]
        assert owner==admin['POSTGRES_USER']
    env={**os.environ,**admin,'DJANGO_SETTINGS_MODULE':'iam_consumer.settings','AICED_CONSUMER_MIGRATION':'1'}
    subprocess.run([sys.executable,'/app/manage.py','migrate','clients','--noinput'],env=env,check=True)
    with db() as c:
        with c.transaction():
            c.execute(sql.SQL('REVOKE ALL ON public.clients_appointment FROM PUBLIC'))
            c.execute(sql.SQL('REVOKE ALL ON public.clients_appointment FROM {}').format(sql.Identifier(config['client']['POSTGRES_USER'])))
            c.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON public.clients_appointment TO {}').format(sql.Identifier(config['client']['POSTGRES_USER'])))
            c.execute(sql.SQL('REVOKE ALL ON public.clients_syntheticimportprojection FROM PUBLIC'))
            c.execute(sql.SQL('REVOKE ALL ON public.clients_syntheticimportprojection FROM {}').format(sql.Identifier(config['client']['POSTGRES_USER'])))
            c.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON public.clients_syntheticimportprojection TO {}').format(sql.Identifier(config['client']['POSTGRES_USER'])))
            c.execute(sql.SQL('REVOKE ALL ON public.clients_syntheticimportjob FROM PUBLIC'))
            c.execute(sql.SQL('REVOKE ALL ON public.clients_syntheticimportjob FROM {}').format(sql.Identifier(config['client']['POSTGRES_USER'])))
            c.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON public.clients_syntheticimportjob TO {}').format(sql.Identifier(config['client']['POSTGRES_USER'])))
    print('Client agenda migration applied; restricted Client-only table credentials retained.')


if __name__=='__main__':apply(json.loads(Path('/private/config.json').read_text()))
