"""Real CP reports vs the exact FT function AND independent 6-sigma arithmetic.

Also compare frozen-kit reports cell by cell and source Guoyu values/limits.
Private source paths, output cells and hashes are retained locally only.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engines/packages/native.pyz'))


def tasks(home):
    return json.loads((home/'validation.json').read_text(encoding='utf8'))


def report(task):
    import openpyxl
    files=[Path(a['path']) for a in task['artifacts'] if a['name'].startswith('files/') and a['name'].endswith('.xlsx')]
    assert len(files)==1
    book=openpyxl.load_workbook(files[0],read_only=True,data_only=True)
    try:return list(book.active.values)
    finally:book.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--frozen-home',type=Path,required=True)
    p.add_argument('--reference-home',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    import numpy as np
    import pandas as pd
    from shared.pat_engine import compute_pat_stats,PAT_HEADERS
    rows=[];frozen={t['parameters']['factory']:t for t in tasks(a.frozen_home)}
    for task in tasks(a.home):
        assert task['status']=='SUCCESS'
        factory=task['parameters']['factory']
        source=[Path(a['path']) for a in task['artifacts'] if a['name'].endswith('PAT_source_manifest.json')][0]
        manifest=json.loads(source.read_text(encoding='utf8'));base=source.parent/'cp-pat-intermediate'
        frames=[pd.read_csv(f,encoding='utf-8-sig') for f in base.rglob('*_cleaned_*.csv')]
        data=pd.concat(frames,ignore_index=True);actual_rows=report(task)
        assert actual_rows==report(frozen[factory]),factory
        actual={r[0]:r for r in actual_rows[2:]}
        checked=0
        for name,spec in manifest['parameters'].items():
            unit,factor=spec['display_unit'],spec['display_factor']
            display=name if unit and (name.endswith(f'[{unit}]') or name.endswith(f'({unit})')) else name+(f' ({unit})' if unit else '')
            values=pd.to_numeric(data[name],errors='coerce').dropna()*factor
            lsl=None if spec['lsl'] is None else spec['lsl']*factor
            usl=None if spec['usl'] is None else spec['usl']*factor
            expected=compute_pat_stats(pd.Series(values.to_numpy(),name=display),lsl,usl)
            row=actual[display]
            for i,key in enumerate(PAT_HEADERS):
                v=expected[key]
                if pd.isna(v):assert row[i] is None,(factory,name,key,row[i])
                elif isinstance(v,str):assert row[i]==v
                else:assert row[i]==float(v) or math.isclose(row[i],float(v),rel_tol=1e-12,abs_tol=1e-9),(factory,name,key,row[i],v)
            q1,median,q3=np.quantile(values.to_numpy(),[.25,.5,.75],method='linear')
            sigma=(q3-q1)/1.35 if q3>q1 else 0
            for index,expected_value in [(5,q1),(6,median),(7,q3),(9,sigma),(10,median-6*sigma),(11,median+6*sigma)]:
                assert math.isclose(row[index],round(float(expected_value),6),rel_tol=1e-12,abs_tol=1e-9)
            assert row[1]==len(values);checked+=len(PAT_HEADERS)
        assert len(data)==manifest['record_count'] and len(actual)==manifest['parameter_count']
        if factory=='GUOYU':
            raw=pd.read_excel(task['sourcePaths'][0],header=None)
            header=raw.index[raw.iloc[:,0].astype(str).eq('Serial#')][0]
            body=raw.iloc[header+1:];body=body[body.iloc[:,0].astype(str).str.fullmatch(r'[PF]\d+',na=False)]
            assert len(body)==len(data)==3266 and manifest['lots']==['25B103']
            for i,name in enumerate(manifest['parameters'],4):
                np.testing.assert_allclose(pd.to_numeric(body.iloc[:,i],errors='coerce').to_numpy(),data[name].to_numpy(),rtol=1e-12,atol=0,equal_nan=True)
            assert manifest['parameters']['CONT2[mV]']['lsl']==0 and manifest['parameters']['CONT2[mV]']['usl']==20
        rows.append(dict(factory=factory,records=len(data),parameters=len(actual),cellsChecked=checked,
                         FTFunctionMatches=True,independentSixSigmaMatches=True,frozenMatches=True,
                         statisticsSha256=manifest['statistics_sha256']))
    references=[]
    for task in tasks(a.reference_home):
        assert task['status']=='SUCCESS';table=report(task)
        if task['parameters']['factory']=='HUAHONG':
            trace=next(Path(item['path']) for item in task['artifacts'] if item['name'].endswith('PAT_source_manifest.json'))
            provenance=json.loads(trace.read_text(encoding='utf8'));assert len(provenance['groups'])==1
            parameters=provenance['groups'][0]['sources'][0]['parameters']
            values={p['name']:[] for p in parameters}
            with zipfile.ZipFile(task['sourcePaths'][0]) as archive:
                for name in archive.namelist():
                    if not name.lower().endswith(('.txt','.dcp')):continue
                    text=archive.read(name)
                    try:text=text.decode('utf-8-sig')
                    except UnicodeDecodeError:text=text.decode('gb18030')
                    lines=[line.split('\t') for line in text.splitlines() if line.strip()]
                    header=next(i for i,line in enumerate(lines) if line[0].strip().upper()=='NO.U')
                    columns=[v.strip() for v in lines[header]]
                    for line in lines[header+1:]:
                        if not line[0].strip().isdigit():continue
                        for p in parameters:values[p['name']].append(line[columns.index(p['name'])])
            actual={r[0]:r for r in table[2:]};cells=0
            for p in parameters:
                label=f"{p['name']} ({p['unit']})"
                series=pd.to_numeric(pd.Series(values[p['name']]),errors='coerce')/p['scale'];series.name=label
                expected=compute_pat_stats(series,p['lsl'],p['usl'])
                for index,key in enumerate(PAT_HEADERS):
                    v=expected[key];observed=actual[label][index]
                    if pd.isna(v):assert observed is None
                    elif isinstance(v,str):assert observed==v
                    else:assert observed==float(v) or math.isclose(observed,float(v),rel_tol=1e-12,abs_tol=1e-9)
                    cells+=1
            references.append(dict(factory='HUAHONG',rawZipMeasurementsMatch=True,parameters=len(parameters),cellsChecked=cells,
                                   statisticsSha256=provenance['statistics_sha256']))
        references.append(dict(factory=task['parameters']['factory'],stage=task['parameters']['stage'],
                               parameters=len(table)-2,package=task['receipt']['package']))
    for task in [*tasks(a.home),*tasks(a.reference_home)]:
        receipt=json.loads((a.home/'results'/task['id']/'receipt.json').read_text(encoding='utf8')) if (a.home/'results'/task['id']/'receipt.json').exists() else json.loads((a.reference_home/'results'/task['id']/'receipt.json').read_text(encoding='utf8'))
        for item in receipt['inputFingerprint']:
            path=Path(task['sourcePaths'][0])
            if path.is_file():
                with path.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==item['sha256']
    cores=[]
    for name in ('native','shared'):
        with zipfile.ZipFile(ROOT/'engines/packages'/f'{name}.pyz') as z:cores.append(hashlib.sha256(z.read('shared/pat_engine.py')).hexdigest())
    assert len(set(cores))==1
    a.output.write_text(json.dumps(dict(status='PASS',CP=rows,referenceExecutions=references,
        sharedStatisticsSha256=cores[0],sourceHashesUnchanged=True),ensure_ascii=False,indent=2),encoding='utf8')
    print('PASS: real CP versus FT function, independent 6-sigma, frozen reports, raw Guoyu values/specs and source hashes')


if __name__=='__main__':main()
