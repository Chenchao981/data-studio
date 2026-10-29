"""Own the original chart helper and all its child processes."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.parse import urlparse
from uuid import uuid4
from .engine import configuration,digest


class Viewers:
    def __init__(self,core):
        self.core=core;self.lock=threading.RLock();self.closed=False;self.sessions={}

    def open(self,task_id):
        task=self.core.task(task_id)
        if task.get('demo') or task['status']!='SUCCESS' or task.get('parameters',{}).get('stage')!='CP' or task['parameters'].get('operation')!='QUICK_CLEAN':
            raise ValueError('请选择成功的CP清洗记录')
        self.core.output(task_id)
        root,manifest=configuration()
        if not manifest.get('viewer',{}).get('files'):raise ValueError('本机图表组件尚未安装')
        for name,checksum in {**manifest['files'],**manifest['viewer']['files']}.items():
            if name.startswith('runtime/') and '/' in name[len('runtime/'):]:continue
            path=(root/name).resolve()
            if not path.is_relative_to(root.resolve()) or digest(path)!=checksum:raise ValueError('图表计算组件校验失败：'+name)
        if task.get('receipt',{}).get('package')!=digest(root/'packages/cp.pyz'):raise ValueError('历史与当前CP图表工具版本不一致')
        with self.lock:
            if self.closed:raise ValueError('客户端已退出')
            previous=self.sessions.get(task_id)
            if previous and previous['process'].poll() is None and previous.get('url'):return previous['url']
            folder=self.core.root/'chart-sessions'/uuid4().hex;folder.mkdir(parents=True)
            code=root/'code'
            env={k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','QT','CONDA','TMS_','PYMS_'))}
            env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',MPLBACKEND='Agg')
            env['PATH']=str(root/'runtime')+';'+os.environ.get('SystemRoot',r'C:\Windows')+'\\System32;'+str(root/'tools')
            env['PYTHONPATH']=os.pathsep.join(map(str,[code,code/'backend',code/'desktop_client',root/'viewer-packages']))
            with (folder/'viewer.log').open('wb') as log:
                process=subprocess.Popen([str(root/'runtime/python.exe'),'-s','-B',str(code/'studio_viewer.py'),str(folder),str(self.core.results/task_id/'engine-work'),task['nativeId']],cwd=folder,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            job=None
            try:
                if os.name=='nt':
                    import win32api,win32job
                    job=win32job.CreateJobObject(None,'')
                    limits=win32job.QueryInformationJobObject(job,win32job.JobObjectExtendedLimitInformation)
                    limits['BasicLimitInformation']['LimitFlags']=win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                    win32job.SetInformationJobObject(job,win32job.JobObjectExtendedLimitInformation,limits)
                    handle=win32api.OpenProcess(0x0100|0x0001,False,process.pid)
                    try:win32job.AssignProcessToJobObject(job,handle)
                    finally:handle.Close()
                entry=dict(process=process,job=job,folder=folder)
                self.sessions[task_id]=entry
                (folder/'go').touch()
            except Exception:
                if job:job.Close()
                process.kill();process.wait();raise
        try:
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                if self.closed or process.poll() is not None:raise ValueError('本地图表启动失败：'+str(folder/'viewer.log'))
                if (folder/'ready.json').exists():
                    url=json.loads((folder/'ready.json').read_text(encoding='utf8'))['url'];parsed=urlparse(url)
                    if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or not parsed.port:raise ValueError('图表地址无效')
                    entry['url']=url
                    return url
                time.sleep(.1)
            raise ValueError('本地图表启动超时：'+str(folder/'viewer.log'))
        except Exception:
            self.stop(entry);raise

    def stop(self,entry):
        (entry['folder']/'stop').touch()
        try:entry['process'].wait(timeout=5)
        except subprocess.TimeoutExpired:entry['process'].kill();entry['process'].wait(timeout=5)
        if entry['job']:entry['job'].Close();entry['job']=None

    def close(self):
        with self.lock:
            self.closed=True
            for entry in self.sessions.values():self.stop(entry)
