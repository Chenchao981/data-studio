"""Exercise registered private samples through the new Studio queue and history."""
import argparse,json,multiprocessing,os,shutil,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from python_core.core import Core
from python_core.tasks import TaskManager
from python_core import engine

# Spawned validation workers import this module as well. The production client
# has no environment override; this hook is confined to the validation harness.
if os.environ.get('STUDIO_VALIDATION_ENGINE_KIT'):
    engine.engine_root=lambda:Path(os.environ['STUDIO_VALIDATION_ENGINE_KIT'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);p.add_argument('--matrix',required=True,type=Path);p.add_argument('--limit',type=int);p.add_argument('--resume',action='store_true');p.add_argument('--keep-going',action='store_true');p.add_argument('--kit',type=Path);a=p.parse_args()
    if a.kit:
        kit=a.kit.resolve();assert (kit/'manifest.json').is_file()
        os.environ['STUDIO_VALIDATION_ENGINE_KIT']=str(kit)
        engine.engine_root=lambda:kit
    cases=json.loads(a.matrix.read_text(encoding='utf8'));cases=cases[:a.limit] if a.limit else cases
    core=Core(a.home);exports=a.home.parent/(a.home.name+'-exports');exports.mkdir(exist_ok=True);core.set_output_directory(str(exports.resolve()));manager=TaskManager(core);ids={};rows=[];native_rows=[]
    if a.resume and (a.home/'validation.json').exists():
        rows=json.loads((a.home/'validation.json').read_text(encoding='utf8'))
        native_rows=json.loads((a.home/'comparison/validation.json').read_text(encoding='utf8'))
        assert len(rows)==len(native_rows)
        for case,row,native in zip(cases,rows,native_rows):
            assert native['title']==case['name']
            if row['status']=='SUCCESS':core.output(row['id'])
            ids[case['name']]=row['id']
        cases=cases[len(rows):]
    expected_by_name={case['name']:case.get('expected_status','SUCCESS') for case in json.loads(a.matrix.read_text(encoding='utf8'))}
    unexpected=[native['title'] for task,native in zip(rows,native_rows) if task['status']!=expected_by_name[native['title']]]
    try:
        for case in cases:
            began=time.perf_counter()
            if case.get('parent'):
                task=core.followup(ids[case['parent']])
            else:
                sources=core.register([s.strip() for s in case['source'].split(';')])
                task=core.create_task(sources[0]['id'],case['code'],[s['id'] for s in sources])
            ids[case['name']]=task['id'];manager.start(task['id']);deadline=time.monotonic()+1200
            while core.task(task['id'])['status'] in {'READY','QUEUED','RUNNING'}:
                manager.tick();time.sleep(.08)
                if time.monotonic()>deadline:raise TimeoutError(case['name'])
            task=core.task(task['id']);expected=case.get('expected_status','SUCCESS')
            task['validationCase']=case['name'];task['validationSeconds']=time.perf_counter()-began
            print(case['name'],task['status'],task.get('warning',''),task['error'][-1000:],flush=True)
            if task['status']!=expected:
                unexpected.append(case['name'])
                if not a.keep_going:raise AssertionError(case['name']+': '+task['error'])
            if task['status']=='SUCCESS':
                core.output(task['id'])
                assert not task.get('tables') and not task.get('previewHash')
                assert not (core.results/task['id']/'preview.sqlite').exists()
                native_id=task['nativeId']
                # The worker's receipt contains original counters; copy only output
                # artifacts to a flat private comparison workspace.
                receipt=json.loads((core.results/task['id']/'receipt.json').read_text(encoding='utf8'))
                native={'id':native_id,'title':case['name'],'status':'SUCCESS','result':receipt['result'],'parent_id': next((r['id'] for r in native_rows if r['title']==case.get('parent')),None)}
                dest=a.home/'comparison/tasks'/native_id/'result';dest.mkdir(parents=True)
                for artifact in task['artifacts']:
                    target=dest/artifact['name'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(artifact['path'],target)
            else:native={'id':task['id'],'title':case['name'],'status':'FAILED','result':None}
            rows.append(task);native_rows.append(native)
            (a.home/'validation.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
            (a.home/'comparison').mkdir(exist_ok=True)
            (a.home/'comparison/validation.json').write_text(json.dumps(native_rows,ensure_ascii=False,indent=2),encoding='utf8')
        again=Core(a.home)
        assert all(again.task(t['id'])['status']==t['status'] for t in rows)
        (a.home/'unexpected.json').write_text(json.dumps(unexpected),encoding='utf8')
        if unexpected:raise AssertionError('Unexpected results: '+', '.join(unexpected))
        print('PASS: real execution, no preview cache, hashes and reopened history',flush=True)
    finally:manager.close()

if __name__=='__main__':multiprocessing.freeze_support();main()
