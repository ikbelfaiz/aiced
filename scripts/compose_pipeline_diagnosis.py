"""Capture full-suite evidence in the disposable Docker stack, without retries."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from compose_context import ROOT, PRIVATE, COMPOSE, TEST

if not TEST:
    raise SystemExit('Use --test; isolated synthetic environment only.')
parser = argparse.ArgumentParser()
parser.add_argument('--test', action='store_true')
parser.add_argument('--label', required=True)
parser.add_argument('spec', nargs='*')
args = parser.parse_args()
if not args.label.replace('-', '').isalnum():
    raise SystemExit('Invalid evidence label')
dest = PRIVATE / ('s161-' + args.label)
dest.mkdir(exist_ok=False)
since = datetime.now(timezone.utc).isoformat()
containers = subprocess.check_output([*COMPOSE, 'ps', '-q'], cwd=ROOT, text=True).split()
with (dest/'stats.jsonl').open('w') as output:
    stats = subprocess.Popen(['docker', 'stats', '--format', '{{json .}}', *containers], stdout=output, stderr=subprocess.DEVNULL)
    try:
        result = subprocess.run([sys.executable, str(ROOT/'scripts/compose_browser.py'), '--test', *args.spec],
                                cwd=ROOT, env=dict(os.environ, AICED_E2E_SCALE='1'))
    finally:
        stats.terminate()
        stats.wait()
        for service in ['gateway', 'commercial', 'client', 'iam', 'db']:
            logs = subprocess.run([*COMPOSE, 'logs', '--since', since, '--no-color', service], cwd=ROOT, capture_output=True)
            (dest/(service+'.log')).write_bytes(logs.stdout+logs.stderr)
        states=subprocess.check_output(['docker','inspect','--format',
            '{{json .Name}} {{json .State}} {{json .RestartCount}}',*containers],cwd=ROOT)
        (dest/'container-states.log').write_bytes(states)
        shutil.copytree(PRIVATE/'browser-compiled', dest/'browser')
        shutil.copyfile(PRIVATE/'browser-compiled.log', dest/'browser.log')
        (dest/'run.json').write_text(json.dumps({'since': since, 'exit_code': result.returncode, 'spec':args.spec}, indent=2))
print('Evidence:', dest, 'exit:', result.returncode)
sys.exit(result.returncode)
