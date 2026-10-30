"""Real-data acceptance for reuse, cancellation, crash recovery and shutdown."""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from python_core import engine
from python_core.core import Core
from python_core.tasks import TaskManager


def main():
    p=argparse.ArgumentParser();p.add_argument('--kit',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    engine.engine_root=lambda:a.kit.resolve()
    core=Core(root/'home');(root/'exports').mkdir();core.set_output_directory(str(root/'exports'))
    manager=TaskManager(core);source=a.source.resolve();before=engine.digest(source);events=[];processes=[]
    def wait(check,timeout=120):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            manager.tick()
            if check():return
            time.sleep(.02)
        raise TimeoutError('Lifecycle check')
    def start(path=source,code='LOCAL_CP_HUAHONG_CLEAN_V1'):
        row=core.register([str(path)])[0];task=core.create_task(row['id'],code)
        manager.start(task['id']);manager.tick();return task['id']
    def finish(id,status):
        wait(lambda:manager.active is None)
        t=core.task(id);assert t['status']==status,t
        if status!='SUCCESS':assert not t.get('publishedDirectory') and not (core.results/id/'analysis-result.zip').exists()
        else:core.output(id)
        events.append(t);return t
    def in_calculation(id):
        return any((core.results/id/'engine-work/tasks').glob('*/staging/files'))
    try:
        wait(lambda:all(w.control and (w.control/'ready.json').exists() for w in manager.warm.workers.values()))
        first=finish(start(),'SUCCESS');pid=first['computeWorker']['pid']
        second=finish(start(),'SUCCESS');assert second['computeWorker']['pid']==pid
        cancelled=start();wait(lambda:in_calculation(cancelled));processes.append(manager.warm.workers['CP'].proc)
        manager.cancel(cancelled);finish(cancelled,'CANCELLED');assert processes[-1].poll() is not None
        after_cancel=finish(start(),'SUCCESS');assert after_cancel['computeWorker']['pid']!=pid
        crashed=start();wait(lambda:in_calculation(crashed));proc=manager.warm.workers['CP'].proc;processes.append(proc)
        proc.kill();finish(crashed,'FAILED')
        recovered=finish(start(),'SUCCESS');assert recovered['computeWorker']['pid']!=proc.pid
        bad=root/'broken.zip';bad.write_bytes(b'not a zip');finish(start(bad),'FAILED')
        finish(start(),'SUCCESS')
        assert engine.digest(source)==before
        processes.extend(w.proc for w in manager.warm.workers.values() if w.proc)
        # Non-pooled analysis must also stop its entire tree when the app closes.
        import psutil
        cold=start(code='LOCAL_CP_HUAHONG_RAW_PAT_V1');wait(lambda:in_calculation(cold))
        children=[p for p in psutil.Process().children(recursive=True) if cold in ' '.join(p.cmdline())]
        assert children
        manager.close()
        assert core.task(cold)['status']=='CANCELLED' and not core.task(cold).get('publishedDirectory')
        assert all(not p.is_running() for p in children)
    finally:manager.close()
    assert all(p.poll() is not None for p in processes)
    (root/'evidence.json').write_text(json.dumps({'status':'PASS','sourceUnchanged':True,'allOwnedProcessesStopped':True,'tasks':events},ensure_ascii=False,indent=2),encoding='utf8')
    print('PASS: same worker reused, cancellation/crash/failure recover, no partial publication, owned processes stop')


if __name__=='__main__':main()
