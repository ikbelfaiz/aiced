"""Run a Django command with the isolated development PostgreSQL environment."""
from pathlib import Path
import json
import os
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
env = os.environ.copy()
env.update(json.loads((root / '.local/postgres/env.json').read_text()))
env['PYTHONPATH'] = str(root / '.tools/python')
raise SystemExit(subprocess.call([sys.executable, str(root / 'backend/manage.py'), *sys.argv[1:]], env=env))
