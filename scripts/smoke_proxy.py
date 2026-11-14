"""Local synthetic-only HTTP smoke test of Vite -> Django session/CSRF behavior."""
import http.cookiejar
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
env = os.environ.copy()
env.update(json.loads((ROOT / '.local/postgres/env.json').read_text()))
if env.get('DJANGO_DEBUG') != '1':
    raise RuntimeError('This smoke test requires the isolated development environment.')
env['PYTHONPATH'] = str(ROOT / '.tools/python')
password = (ROOT / '.local/postgres/seed-password').read_text()
flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


backend_port = free_port()
frontend_port = free_port()
base = f'http://127.0.0.1:{frontend_port}'
env['API_PROXY_TARGET'] = f'http://127.0.0.1:{backend_port}'
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(path, method='GET', data=None, csrf=None, origin=None):
    headers = {'Accept': 'application/json'}
    if csrf:
        headers['X-CSRFToken'] = csrf
    if origin:
        headers['Origin'] = origin
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base + path, json.dumps(data).encode() if data is not None else None, headers, method=method)
    try:
        response = opener.open(req, timeout=3)
    except urllib.error.HTTPError as exc:
        response = exc
    body = response.read()
    return response.status, json.loads(body) if body else None


processes = []
try:
    with (ROOT / '.local/proxy-backend.log').open('w') as backend_log, (ROOT / '.local/proxy-frontend.log').open('w') as frontend_log:
        processes.append(subprocess.Popen([sys.executable, str(ROOT / 'backend/manage.py'), 'runserver',
                                           f'127.0.0.1:{backend_port}', '--noreload'], cwd=ROOT, env=env,
                                          stdout=backend_log, stderr=subprocess.STDOUT, creationflags=flags))
        processes.append(subprocess.Popen([str(ROOT / '.tools/node.exe'), str(ROOT / 'frontend/node_modules/vite/bin/vite.js'),
                                           '--host', '127.0.0.1', '--port', str(frontend_port), '--strictPort'],
                                          cwd=ROOT / 'frontend', env=env, stdout=frontend_log,
                                          stderr=subprocess.STDOUT, creationflags=flags))
        deadline = time.monotonic() + 20
        while True:
            try:
                if request('/api/health/') == (200, {'status': 'ok'}):
                    break
            except (OSError, ValueError):
                pass
            if time.monotonic() >= deadline or any(proc.poll() is not None for proc in processes):
                raise RuntimeError('Local servers did not become ready; inspect .local/proxy-*.log.')
            time.sleep(0.1)
        assert request('/api/session/')[0] == 403
        csrf = request('/api/auth/csrf/')[1]['csrfToken']
        credentials = {'username': 'synthetic.reader.a', 'password': password}
        assert request('/api/auth/login/', 'POST', credentials, csrf, 'http://untrusted.example')[0] == 403
        assert request('/api/auth/login/', 'POST', credentials, csrf, base)[0] == 200
        csrf = request('/api/auth/csrf/')[1]['csrfToken']
        assert request('/api/session/')[0] == 200
        status, clients = request('/api/clients/')
        assert status == 200 and clients['count'] == 1
        party_id = clients['results'][0]['id']
        assert request(f'/api/clients/{party_id}/accounts/')[0] == 403
        assert request('/api/auth/logout/', 'POST', csrf=csrf, origin=base)[0] == 204
        assert request('/api/session/')[0] == 403
        print('PASS: real Vite proxy, health, anonymous denial, Origin/CSRF, session login, client scope, financial denial and logout.')
finally:
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    for proc in processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
