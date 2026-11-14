from pathlib import Path
import json
import pymupdf
import openpyxl
root=Path(__file__).resolve().parents[1]
out=root/'.local/reference-review'
out.mkdir(parents=True,exist_ok=True)
for path in (root/'references').glob('*.pdf'):
    doc=pymupdf.open(path)
    text='\n'.join(f'\n--- PAGE {i+1} ---\n'+page.get_text() for i,page in enumerate(doc))
    (out/(path.stem+'.txt')).write_text(text,encoding='utf-8')
    print(path.name, 'pages',len(doc),'text characters',len(text))
    extra = {'Mode opératoire Carthago Référentiel_AI_VF': [52, 57, 66], 'Mode opératoire Carthago Titres_AI-VF': [8, 96]}
    for i in sorted(set([0,min(2,len(doc)-1),min(5,len(doc)-1)] + extra.get(path.stem, []))):
        doc[i].get_pixmap(matrix=pymupdf.Matrix(1,1)).save(str(out/(path.stem+f'-{i+1}.png')))
for path in (root/'references').glob('*.xlsx'):
    wb=openpyxl.load_workbook(path,read_only=True,data_only=False)
    print('\nWORKBOOK',path.name)
    for ws in wb:
        print('SHEET',ws.title,'rows',ws.max_row,'columns',ws.max_column)
        for row in ws.iter_rows(min_row=1,max_row=min(3,ws.max_row)):
            print(json.dumps([{'column':c.column,'value':str(c.value) if c.row==1 else None,'type':c.data_type,'format':c.number_format} for c in row if c.value is not None],ensure_ascii=False))
