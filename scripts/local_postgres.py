"""Initialize an isolated loopback-only development cluster; never touches an installed service."""
from pathlib import Path
import json
import os
import secrets
import subprocess
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tools/python'))
import psycopg
from psycopg import sql

local = ROOT / '.local/postgres'
local.mkdir(parents=True, exist_ok=True)
binary = ROOT / '.tools/pgsql/bin'
if not binary.exists():
    with ZipFile(ROOT / '.tools/postgresql.zip') as archive:
        for info in archive.infolist():
            if info.filename.startswith(('pgsql/bin/', 'pgsql/lib/', 'pgsql/share/')):
                archive.extract(info, ROOT / '.tools')

flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def run(name, *args):
    subprocess.run([str(binary / (name + '.exe')), *map(str, args)], check=True, creationflags=flags)


credentials = local / 'credentials.json'
if not credentials.exists():
    credentials.write_text(json.dumps({'owner': secrets.token_urlsafe(36), 'app': secrets.token_urlsafe(36)}))
passwords = json.loads(credentials.read_text())
data = local / 'data'
if not (data / 'PG_VERSION').exists():
    password_file = local / 'init-password'
    password_file.write_text(passwords['owner'])
    try:
        run('initdb', '-D', data, '-U', 'aiced_owner', '--pwfile', password_file,
            '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C')
    finally:
        password_file.unlink(missing_ok=True)
if not (data / 'postmaster.pid').exists():
    run('pg_ctl', '-D', data, '-l', local / 'server.log', '-o', '-h 127.0.0.1 -p 55432', '-w', 'start')
with psycopg.connect(host='127.0.0.1', port=55432, user='aiced_owner', password=passwords['owner'], dbname='postgres', autocommit=True) as conn:
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='aiced'").fetchone():
        conn.execute(sql.SQL('CREATE ROLE aiced LOGIN CREATEDB PASSWORD {}').format(sql.Literal(passwords['app'])))
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname='aiced'").fetchone():
        conn.execute('CREATE DATABASE aiced OWNER aiced')
env_file = local / 'env.json'
old_env = json.loads(env_file.read_text()) if env_file.exists() else {}
env = {'POSTGRES_HOST': '127.0.0.1', 'POSTGRES_PORT': '55432', 'POSTGRES_USER': 'aiced',
       'POSTGRES_DB': 'aiced', 'POSTGRES_PASSWORD': passwords['app'],
       'DJANGO_SECRET_KEY': old_env.get('DJANGO_SECRET_KEY') or secrets.token_urlsafe(50), 'DJANGO_DEBUG': '1'}
env_file.write_text(json.dumps(env))
print('Isolated PostgreSQL ready on 127.0.0.1:55432; private environment in .local/postgres/env.json')
