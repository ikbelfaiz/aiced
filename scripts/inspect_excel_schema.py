"""Local schema inspection only: never print or import reference record values."""
import json
import sys
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.tools/python'))
import openpyxl

report=[]
for path in sorted((ROOT/'references').glob('*.xlsx')):
    book=openpyxl.load_workbook(path,read_only=True,data_only=False)
    for sheet in book:
        rows=sheet.iter_rows(values_only=True)
        headers=list(next(rows))
        types=[Counter() for _ in headers]
        for row in rows:
            for index,value in enumerate(row[:len(headers)]):
                types[index][type(value).__name__]+=1
        report.append({'file':path.name,'sheet':sheet.title,'dimensions':[sheet.max_row,sheet.max_column],
                       'columns':[{'position':index+1,'header':header,'observed_types':dict(types[index])} for index,header in enumerate(headers)]})
    book.close()
output=ROOT/'.local/ui-review/excel-schema.json'
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('Schema metadata written privately to .local/ui-review/excel-schema.json. No record values exported.')
