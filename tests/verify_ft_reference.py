"""Compare Studio output with direct, isolated calls into an approved FT PYZ.

Private source paths live only in the supplied matrix. Worksheet XML, styles,
shared strings and formulas must match exactly; ZIP dates/core creation times
are not business data. No output workbook is opened in the product UI.
"""
import argparse,hashlib,importlib,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def direct(case,package,root):
    sys.path.insert(0,str(package.resolve()))
    output=root/'output';output.mkdir(parents=True,exist_ok=True)
    assert not any(output.iterdir()),'Refusing to overwrite reference output'
    sources=[Path(s) for s in case['source'].split(';')]
    if len(sources)==1 and sources[0].is_dir():source=sources[0]
    else:
        source=root/'input';source.mkdir(exist_ok=True)
        for item in sources:shutil.copyfile(item,source/item.name)
    try:
        code=case['code']
        if code=='LOCAL_FT_JIEMIN_RAW_PAT_V1':
            from factories.jiemin.pat_cleaner import generate_raw_pat
            result=generate_raw_pat(str(source),str(output))
        else:
            factory,module,cls,method={
                'LOCAL_FT_JIEMIN_FT_ALL_V1':('jiemin','dc_cleaner','JieminFTCleaner','process_all'),
                'LOCAL_FT_JIEMIN_DVDS_V1':('jiemin','dvds_cleaner','JieminDVDSCleaner','process_all'),
                'LOCAL_FT_JIEMIN_RG_V1':('jiemin','rg_cleaner','JieminRGCleaner','process_all'),
                'LOCAL_FT_RIYUEXIN_DC_V1':('riyuexin','dc_cleaner','DCDataCleaner','process_all_dc_files'),
                'LOCAL_FT_DIANJI_FT_ALL_V1':('dianji','dc_cleaner','DianjiDCCleaner','process_all'),
            }[code]
            mod=importlib.import_module(f'factories.{factory}.{module}')
            assert str(package.resolve()) in mod.__file__
            cleaner=getattr(mod,cls)(input_dir=str(source),output_dir=str(output))
            result=getattr(cleaner,method)()
        assert result,'Original cleaner returned no result'
        status='SUCCESS';error=''
    except Exception as exc:status='FAILED';error=str(exc)
    files=[dict(path=str(p.resolve()),sha256=sha(p)) for p in output.rglob('*.xlsx')]
    assert status==case.get('expected_status','SUCCESS'),error
    if status=='FAILED':assert not files,'Partial reference output'
    (root/'reference.json').write_text(json.dumps(dict(status=status,error=error,files=files),ensure_ascii=False,indent=2),encoding='utf8')

def compare(case,reference,task):
    assert reference['status']==task['status']
    if task['status']=='FAILED':
        assert not task.get('artifacts')
        return dict(name=case['name'],status='PASS',expected_rejection=True)
    expected=reference['files'];actual=[a for a in task['artifacts'] if a['name'].endswith('.xlsx')]
    assert len(expected)==len(actual)==1,(case['name'],len(expected),len(actual))
    left=Path(expected[0]['path']);right=Path(actual[0]['path']);assert sha(left)==expected[0]['sha256']
    matched=[]
    with zipfile.ZipFile(left) as a,zipfile.ZipFile(right) as b:
        names={n for n in a.namelist() if n.startswith('xl/')}
        assert names=={n for n in b.namelist() if n.startswith('xl/')}
        for n in sorted(names):
            with a.open(n) as x,b.open(n) as y:
                assert hashlib.file_digest(x,'sha256').digest()==hashlib.file_digest(y,'sha256').digest(),(case['name'],n)
            matched.append(n)
    return dict(name=case['name'],status='PASS',exact_workbook_parts=matched)

def main():
    p=argparse.ArgumentParser();p.add_argument('--matrix',type=Path,required=True);p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--case',type=int);p.add_argument('--studio',type=Path);a=p.parse_args()
    cases=json.loads(a.matrix.read_text(encoding='utf8'));a.output.mkdir(parents=True,exist_ok=True)
    if a.case is not None:return direct(cases[a.case],a.package,a.output/cases[a.case]['name'])
    if not a.studio:
        for i,case in enumerate(cases):
            folder=a.output/case['name'];folder.mkdir(exist_ok=True)
            if (folder/'reference.json').exists():
                saved=json.loads((folder/'reference.json').read_text(encoding='utf8'))
                assert saved['status']==case.get('expected_status','SUCCESS')
                assert all(sha(Path(f['path']))==f['sha256'] for f in saved['files'])
                continue
            with (folder/'execution.log').open('w',encoding='utf8') as log:
                subprocess.run([sys.executable,__file__,'--matrix',str(a.matrix),'--package',str(a.package),'--output',str(a.output),'--case',str(i)],check=True,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONUTF8':'1'})
            print('REFERENCE PASS',case['name'],flush=True)
    else:
        tasks=json.loads((a.studio/'validation.json').read_text(encoding='utf8'));assert len(tasks)==len(cases)
        results=[]
        for case,task in zip(cases,tasks):
            assert case['name']==task['validationCase']
            reference=json.loads((a.output/case['name']/'reference.json').read_text(encoding='utf8'))
            results.append(compare(case,reference,task));print('COMPARE PASS',case['name'],flush=True)
        (a.output/('comparison-'+a.studio.name+'.json')).write_text(json.dumps(results,indent=2),encoding='utf8')

if __name__=='__main__':main()
