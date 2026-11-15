"""Run existing Chromium suites against Compose; never starts a local server."""
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.tools/python'),str(ROOT/'backend')]
import openpyxl
from ingestion.templates import TEMPLATES
import uuid

cfg=json.loads((ROOT/'.local/s7/config.json').read_text())
dest=ROOT/'.local/ui-review'
dest.mkdir(parents=True,exist_ok=True)
book=openpyxl.Workbook()
sheet=book.active
sheet.title='Tier'
sheet.append(TEMPLATES['legal']['headers'])
for key in ['SYNTH-'+str(uuid.uuid4()),'SYNTH-DUP','SYNTH-DUP']:
    row=[None]*25
    row[1]=key
    row[3]='SOCIÉTÉ SYNTHÉTIQUE TEST NAVIGATEUR'
    row[4]='13/02/2026'
    sheet.append(row)
book.save(dest/'synthetic-legal.xlsx')
development='--development' in sys.argv
env=dict(os.environ,AICED_E2E_URL='http://127.0.0.1:5187',
         AICED_E2E_PASSWORD=cfg['admin']['AICED_SEED_PASSWORD'],
         AICED_E2E_PRODUCTION='1',AICED_E2E_REPORT_DIR=str(ROOT/('.local/s7/browser-development' if development else '.local/s7/browser-compiled')))
if development: env.pop('AICED_E2E_PRODUCTION',None)
with (ROOT/('.local/s7/browser-development.log' if development else '.local/s7/browser-compiled.log')).open('wb') as log:
    result=subprocess.run([str(ROOT/'.tools/node.exe'),str(ROOT/'frontend/node_modules/@playwright/test/cli.js'),'test'],
                          cwd=ROOT/'frontend',env=env,stdout=log,stderr=log)
print('Compose Chromium suite exit:',result.returncode)
sys.exit(result.returncode)
