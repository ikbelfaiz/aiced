"""Run Chromium against isolated local Django/Vite and synthetic seed accounts only."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import argparse
from contextlib import ExitStack

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
env = os.environ.copy()
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--rehearsal-env',type=Path)
parser.add_argument('--rehearsal-password',type=Path)
parser.add_argument('--report-directory',type=Path)
parser.add_argument('--gateway', action='store_true')
options,remaining_args=parser.parse_known_args()
env.update(json.loads((options.rehearsal_env or ROOT / '.local/postgres/env.json').read_text()))
if options.rehearsal_env:
    sys.path.insert(0,str(ROOT/'backend'))
    from testing.rehearsal import validate_environment
    validate_environment(env)
    if not options.rehearsal_password:
        raise RuntimeError('Explicit synthetic rehearsal password file required.')
if env.get('DJANGO_DEBUG') != '1':
    raise RuntimeError('Synthetic development environment required.')
env['PYTHONPATH'] = str(ROOT / '.tools/python')
env['PATH'] = str(ROOT / '.tools') + os.pathsep + env.get('PATH', '')
env['AICED_E2E_PASSWORD'] = (options.rehearsal_password or ROOT / '.local/postgres/seed-password').read_text()
report_directory=options.report_directory or ROOT/'.local'
report_directory.mkdir(parents=True,exist_ok=True)
if options.report_directory:
    env['AICED_E2E_REPORT_DIR']=str(report_directory.resolve())
sys.path.insert(0,str(ROOT/'.tools/python'))
sys.path.insert(0,str(ROOT/'backend'))
from ingestion.templates import TEMPLATES
from testing.gateway import nginx_gateway
import openpyxl
import uuid
book=openpyxl.Workbook(); sheet=book.active; sheet.title='Tier'
sheet.append(TEMPLATES['legal']['headers'])
for key in [f'SYNTH-{uuid.uuid4()}','SYNTH-DUP','SYNTH-DUP']:
    row=[None]*25;row[1]=key;row[3]='SOCIÉTÉ SYNTHÉTIQUE TEST NAVIGATEUR';row[4]='13/02/2026';sheet.append(row)
book.save(ROOT/'.local/ui-review/synthetic-legal.xlsx')
# Repeated synthetic browser runs must not exhaust the ordinary development budget.
# Overrides apply only to this short-lived test server; security tests use real limits.
env['LOGIN_ACCOUNT_LIMIT'] = '1000'
env['LOGIN_IP_LIMIT'] = '2000'
env['IMPORT_MAX_DAILY_BATCHES'] = '2000'
env['IMPORT_MAX_STAGED_BATCHES'] = '1000'
flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]
backend_port, frontend_port = port(), port()
if options.gateway:
    import secrets
    env['AICED_GATEWAY_KEY'] = secrets.token_urlsafe(48)
production = '--production' in remaining_args
test_args = [arg for arg in remaining_args if arg != '--production']
if production:
    env['AICED_E2E_PRODUCTION'] = '1'
env['API_PROXY_TARGET'] = f'http://127.0.0.1:{backend_port}'
env['AICED_E2E_URL'] = f'http://127.0.0.1:{frontend_port}'
processes = []
stack = ExitStack()
try:
    with (report_directory / 'e2e-backend.log').open('w') as back, (report_directory / 'e2e-frontend.log').open('w') as front:
        processes.append(subprocess.Popen([sys.executable, str(ROOT/'backend/manage.py'), 'runserver', f'127.0.0.1:{backend_port}', '--noreload'], cwd=ROOT, env=env, stdout=back, stderr=subprocess.STDOUT, creationflags=flags))
        processes.append(subprocess.Popen([str(ROOT/'.tools/node.exe'),str(ROOT/'frontend/node_modules/vite/bin/vite.js'),*(['preview'] if production else []),'--host','127.0.0.1','--port',str(frontend_port),'--strictPort'], cwd=ROOT/'frontend',env=env,stdout=front,stderr=subprocess.STDOUT,creationflags=flags))
        if options.gateway:
            env['AICED_E2E_URL'] = stack.enter_context(nginx_gateway(
                report_directory/'gateway', f'127.0.0.1:{backend_port}',
                f'127.0.0.1:{frontend_port}', env['AICED_GATEWAY_KEY']))
        deadline=time.monotonic()+30
        while True:
            try:
                with urllib.request.urlopen(env['AICED_E2E_URL']+'/api/health/',timeout=2) as response:
                    if response.status==200: break
            except OSError: pass
            if time.monotonic()>deadline: raise RuntimeError('Servers unavailable: see .local/e2e-*.log')
            time.sleep(.2)
        result=subprocess.run([str(ROOT/'.tools/node.exe'),str(ROOT/'frontend/node_modules/@playwright/test/cli.js'),'test',*test_args],cwd=ROOT/'frontend',env=env,creationflags=flags,capture_output=True)
        (report_directory/'e2e-output.log').write_bytes(result.stdout + result.stderr)
        print(result.stdout.decode('utf-8',errors='replace'), flush=True)
        print(result.stderr.decode('utf-8',errors='replace'), flush=True)
        sys.exit(result.returncode)
finally:
    stack.close()
    for proc in processes:
        if proc.poll() is None: proc.terminate()
    for proc in processes:
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
