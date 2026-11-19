"""Run existing Chromium suites against Compose; never starts a local server."""
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
import argparse
ROOT=Path(__file__).resolve().parents[1]
from compose_context import PRIVATE, URL
sys.path[:0]=[str(ROOT/'.tools/python'),str(ROOT/'backend')]
import openpyxl
from ingestion.templates import TEMPLATES
import uuid
import hashlib

cfg=json.loads((PRIVATE/'config.json').read_text())
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

# All three positional source contracts, synthetic values only. Regenerated per run.
expected={}
for template,spec in TEMPLATES.items():
    book=openpyxl.Workbook()
    sheet=book.active
    sheet.title=spec['sheet']
    sheet.append(spec['headers'])
    row=[None]*len(spec['headers'])
    for position in spec['candidate_keys']:
        row[position-1]='SYNTH-REVIEW-'+uuid.uuid4().hex
    if template=='physical':
        row[2]='SYNTHETIQUE';row[3]='PERSONNE';row[8]='02/01/2000'
    elif template=='legal': row[3]='SOCIETE SYNTHETIQUE SANS DONNEE REELLE'
    else:
        row[3]='DETENTEUR SYNTHETIQUE NON RAPPROCHE'
        row[8]='02/01/2024'
    sheet.append(row)
    book.save(dest/f'synthetic-review-{template}.xlsx')
    expected[template]={'cells':{str(i+1):value for i,value in enumerate(row)},'digest':hashlib.sha256((dest/f'synthetic-review-{template}.xlsx').read_bytes()).hexdigest()}
(PRIVATE/'import-dashboard-expected.json').write_text(json.dumps(expected,indent=2),encoding='utf-8')
development='--development' in sys.argv
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--test',action='store_true')
parser.add_argument('--development',action='store_true')
_,playwright_args=parser.parse_known_args()
env=dict(os.environ,AICED_E2E_URL=URL,
         AICED_E2E_PASSWORD=cfg['admin']['AICED_SEED_PASSWORD'],
         AICED_E2E_PRODUCTION='1',AICED_E2E_REPORT_DIR=str(PRIVATE/('browser-development' if development else 'browser-compiled')))
if development: env.pop('AICED_E2E_PRODUCTION',None)
if '--test' in sys.argv: env['AICED_E2E_ISOLATED']='1'
else: env.pop('AICED_E2E_ISOLATED',None)
report_directory=Path(env['AICED_E2E_REPORT_DIR'])
report_directory.mkdir(parents=True,exist_ok=True)
# Evidence belongs to this invocation; never mix earlier request lifecycles.
(report_directory/'pipeline-requests.jsonl').unlink(missing_ok=True)
with (PRIVATE/('browser-development.log' if development else 'browser-compiled.log')).open('wb') as log:
    node=os.environ.get('AICED_NODE_BINARY') or (str(ROOT/'.tools/node.exe') if (ROOT/'.tools/node.exe').exists() else shutil.which('node'))
    if not node: raise RuntimeError('Node 22+ is required for the browser runner.')
    result=subprocess.run([node,str(ROOT/'frontend/node_modules/@playwright/test/cli.js'),'test',*playwright_args],
                          cwd=ROOT/'frontend',env=env,stdout=log,stderr=log)
print('Compose Chromium suite exit:',result.returncode)
sys.exit(result.returncode)
