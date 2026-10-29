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


def run_real(task, folder, messages, cancelled):
    root = Path(folder)/task['id']
    proc = None
    try:
        engine, manifest = configuration()
        if task['engineHash'] != digest(engine/'manifest.json'):
            raise ValueError('计算组件在任务创建后改变，请新建任务')
        for name, checksum in manifest['files'].items():
            # Full runtime is verified when the kit is prepared. Rechecking
            # 14k library files for every task makes small jobs needlessly slow.
            if name.startswith('runtime/') and '/' in name[len('runtime/'):]:
                continue
            if cancelled.is_set():raise ValueError('已取消组件校验')
            path = (engine/name).resolve()
            if not path.is_relative_to(engine.resolve()) or digest(path) != checksum:
                raise ValueError('计算组件校验失败：'+name)
        root.mkdir(exist_ok=False)
        (root/'request.json').write_text(json.dumps(task, ensure_ascii=False), encoding='utf8')
        env = {k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','QT','CONDA','TMS_','PYMS_'))}
        env.update(PYTHONUTF8='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', MPLBACKEND='Agg')
        env['PATH'] = str(engine/'runtime')+';'+str(engine/'runtime/Scripts')+';'+os.environ.get('SystemRoot',r'C:\Windows')+'\\System32;'+str(engine/'tools')
        code = engine/'code'
        env['PYTHONPATH'] = os.pathsep.join(map(str,[code,code/'backend',code/'desktop_client']))
        messages.put({'progress': 5, 'phase': '校验原始数据与计算规则'})
        with (root/'execution.log').open('w',encoding='utf8') as log:
            proc = subprocess.Popen([str(engine/'runtime/python.exe'),'-s','-B',str(code/'studio_runner.py'),str(root)],env=env,cwd=root,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            started = time.monotonic()
            stopping = None
            last_progress = None
            while proc.poll() is None:
                if cancelled.is_set():
                    (root/'cancel').touch()
                    stopping = stopping or time.monotonic()
                    if time.monotonic()-stopping > 15:
                        raise ValueError('用户取消，计算进程已停止')
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
        if outcome['status'] != 'SUCCESS':
            raise ValueError(outcome.get('error','计算未完成'))
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
        messages.put(outcome)
    except BaseException as exc:
        messages.put({'status':'CANCELLED' if cancelled.is_set() else 'FAILED','error':str(exc),'phase':'执行结束'})
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
