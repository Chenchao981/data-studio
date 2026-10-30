"""Pinned, relocatable engine transport; the UI never imports legacy Qt code."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from functools import lru_cache


def engine_root():
    return (Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]) / 'engines'


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def configuration():
    root = engine_root()
    record = json.loads((root/'manifest.json').read_text(encoding='utf8'))
    return root, record


@lru_cache(maxsize=2)
def _catalog(path, modified, size):
    record=json.loads(Path(path).read_text(encoding='utf8'))
    return {'ready': True, 'tools': record['tools'], 'version': record['version'], 'error': ''}


def catalog():
    try:
        root=engine_root()
        if not (root/'runtime/python.exe').is_file():
            raise ValueError('缺少独立计算环境')
        path=root/'manifest.json';stamp=path.stat()
        # Cache presentation metadata only. Task creation/execution still reads
        # and hashes the full manifest and verifies engine files independently.
        return _catalog(str(path),stamp.st_mtime_ns,stamp.st_size)
    except (OSError, ValueError, KeyError) as exc:
        return {'ready': False, 'tools': [], 'version': '', 'error': f'计算组件未就绪：{exc}'}


def environment(engine):
    env={k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','QT','CONDA','TMS_','PYMS_'))}
    env.update(PYTHONUTF8='1',PYTHONUNBUFFERED='1',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',MPLBACKEND='Agg')
    env['PATH']=str(engine/'runtime')+';'+str(engine/'runtime/Scripts')+';'+os.environ.get('SystemRoot',r'C:\Windows')+'\\System32;'+str(engine/'tools')
    code=engine/'code'
    env['PYTHONPATH']=os.pathsep.join(map(str,[code,code/'backend',code/'desktop_client']))
    return env


def verify_components(engine,manifest,cancelled=None):
    for name,checksum in manifest['files'].items():
        if name.startswith('runtime/') and '/' in name[len('runtime/'):]:continue
        if cancelled and cancelled.is_set():raise InterruptedError('已取消组件校验')
        path=(engine/name).resolve()
        if not path.is_relative_to(engine.resolve()) or digest(path)!=checksum:
            raise ValueError('计算组件校验失败：'+name)


def run_real(task, folder, messages, cancelled, warm=None):
    root = Path(folder)/task['id']
    proc = None
    tree = None
    try:
        began = time.perf_counter()
        engine, manifest = configuration()
        root.mkdir(exist_ok=False)
        (root/'execution.log').write_text('正在校验固定计算组件…\n',encoding='utf8')
        if task['engineHash'] != digest(engine/'manifest.json'):
            raise ValueError('计算组件在任务创建后改变，请新建任务')
        verify_components(engine,manifest,cancelled)
        verified = time.perf_counter()
        (root/'request.json').write_text(json.dumps(task, ensure_ascii=False), encoding='utf8')
        env = environment(engine)
        code = engine/'code'
        env['PYTHONPATH'] = os.pathsep.join(map(str,[code,code/'backend',code/'desktop_client']))
        messages.put({'progress': 5, 'phase': '校验原始数据与计算规则'})
        spec=next(t for t in manifest['tools'] if t['tool_code']==task['toolCode'])
        reusable=spec.get('profile')=='native' or (spec.get('profile')=='shared' and spec['test_stage']=='FT' and spec['factory_code']=='RIYUEGUANG')
        key=spec['test_stage']+('-shared' if spec.get('profile')=='shared' else '')
        worker=warm.workers.get(key) if warm and reusable and spec['analysis_type']=='QUICK_CLEAN' else None
        worker_receipt=None
        if worker:
            worker_receipt=worker.run(root,cancelled,messages)
        else:
          with (root/'execution.log').open('a',encoding='utf8') as log:
            proc = subprocess.Popen([str(engine/'runtime/python.exe'),'-s','-B',str(code/'studio_runner.py'),str(root)],env=env,cwd=root,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),start_new_session=os.name!='nt')
            from .warm_engine import ProcessTree
            tree=ProcessTree(proc)
            started = time.monotonic()
            last_progress = None
            while proc.poll() is None:
                if cancelled.is_set():
                    (root/'cancel').touch()
                    tree.close()
                    break
                if time.monotonic()-started > 4*3600+180:
                    raise ValueError('计算超过4小时时限')
                progress = root/'progress.json'
                if progress.exists():
                    try:
                        current = json.loads(progress.read_text(encoding='utf8'))
                        if current != last_progress:
                            messages.put(current)
                            last_progress = current
                    except (OSError, ValueError): pass
                time.sleep(.5)
        if cancelled.is_set():
            messages.put({'status':'CANCELLED','error':'用户取消任务，未发布部分输出'})
            return
        outcome = json.loads((root/'outcome.json').read_text(encoding='utf8'))
        if worker_receipt:outcome['computeWorker']=worker_receipt
        if outcome['status'] != 'SUCCESS':
            raise ValueError(outcome.get('error','计算未完成'))
        calculated = time.perf_counter()
        if task.get('outputParent'):
            from .publishing import publish
            messages.put({'progress':97,'phase':'正在保存到所选输出目录'})
            try:
                outcome.update(publish({**task,**outcome},Path(folder).parent,cancelled))
            except InterruptedError:
                messages.put({'status':'CANCELLED','error':'用户取消保存，未发布输出文件夹'})
                return
            except Exception as exc:
                outcome['warning']='；'.join(filter(None,[outcome.get('warning'),'清洗完成，但保存输出目录失败：'+str(exc)+'。可从历史查看或另存结果。']))
            (root/'outcome.json').write_text(json.dumps(outcome,ensure_ascii=False),encoding='utf8')
        outcome['transportTiming'] = {'verify':round(verified-began,4),'runner':round(calculated-verified,4),'publish':round(time.perf_counter()-calculated,4)}
        messages.put(outcome)
    except BaseException as exc:
        messages.put({'status':'CANCELLED' if cancelled.is_set() else 'FAILED','error':str(exc),'phase':'执行结束'})
    finally:
        if tree:tree.close()
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
