"""Owned CP/FT worker processes, warmed off the UI thread and reused serially."""
from __future__ import annotations
import json, os, subprocess, threading, time, uuid
from pathlib import Path


class ProcessTree:
    def __init__(self, process):
        self.process=process;self.job=None
        if os.name=='nt':
            import win32api,win32job
            self.job=win32job.CreateJobObject(None,'')
            info=win32job.QueryInformationJobObject(self.job,win32job.JobObjectExtendedLimitInformation)
            info['BasicLimitInformation']['LimitFlags']=win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(self.job,win32job.JobObjectExtendedLimitInformation,info)
            handle=win32api.OpenProcess(0x0100|0x0001,False,process.pid)
            try:win32job.AssignProcessToJobObject(self.job,handle)
            except BaseException:
                self.job.Close();self.job=None;process.kill();raise
            finally:handle.Close()

    def close(self):
        if self.job is not None:self.job.Close();self.job=None
        elif os.name!='nt' and self.process.poll() is None:
            import signal
            os.killpg(self.process.pid,signal.SIGKILL)
        if self.process.poll() is None:self.process.kill()
        self.process.wait(timeout=5)


class Worker:
    def __init__(self, engine, home, stage):
        self.engine=engine;self.home=home;self.stage=stage
        self.lock=threading.RLock();self.proc=None;self.tree=None;self.closed=False
        self.version='';self.control=None;self.error='';self.ready=False

    def stop(self):
        self.ready=False
        if self.tree:self.tree.close();self.tree=None
        if self.proc:
            if self.proc.stdin:self.proc.stdin.close()
            self.proc=None

    def ensure(self):
        from .engine import digest, environment, verify_components
        version=digest(self.engine/'manifest.json')
        if self.proc and self.proc.poll() is None and version==self.version:return
        self.stop()
        if self.closed:raise InterruptedError('客户端正在关闭')
        manifest=json.loads((self.engine/'manifest.json').read_text(encoding='utf8'))
        verify_components(self.engine,manifest)
        self.control=self.home/(self.stage+'-'+uuid.uuid4().hex)
        self.control.mkdir(parents=True)
        env=environment(self.engine)
        env.update(CP_DATA_ROOT=str(self.control/'cp-data'),CP_LOG_DIR=str(self.control/'cp-data/logs'),CP_CONFIG_DIR=str(self.control/'cp-data/config'),MPLCONFIGDIR=str(self.control/'matplotlib'),NUMEXPR_MAX_THREADS='8')
        with (self.control/'warmup.log').open('w',encoding='utf8') as log:
            self.proc=subprocess.Popen([str(self.engine/'runtime/python.exe'),'-s','-B','-u',str(self.engine/'code/studio_service.py'),self.stage,str(self.control)],env=env,cwd=self.control,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True,encoding='utf8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),start_new_session=os.name!='nt')
        self.tree=ProcessTree(self.proc)
        (self.control/'go').touch()
        deadline=time.monotonic()+120
        while not (self.control/'ready.json').exists():
            if self.closed or self.proc.poll() is not None or time.monotonic()>deadline:
                tail=(self.control/'warmup.log').read_text(encoding='utf8',errors='replace')[-2000:]
                self.stop();raise RuntimeError('计算引擎预热未完成：'+tail)
            time.sleep(.05)
        ready=json.loads((self.control/'ready.json').read_text(encoding='utf8'))
        if ready['engineHash']!=version or ready['pid']!=self.proc.pid:
            self.stop();raise ValueError('预热计算组件身份不一致')
        self.version=version
        self.ready=True

    def prewarm(self):
        with self.lock:
            try:self.ensure()
            except Exception as exc:self.error=str(exc)

    def run(self, folder, cancelled, messages):
        if not self.ready:
            messages.put({'phase':'等待清洗引擎预热','progress':5})
            with (folder/'execution.log').open('a',encoding='utf8') as log:log.write('清洗引擎正在预热，请稍候…\n')
        with self.lock:
            try:
                self.ensure()
                if cancelled.is_set():raise InterruptedError('用户取消任务')
                self.proc.stdin.write(json.dumps({'folder':str(folder.resolve()),'engineHash':self.version})+'\n');self.proc.stdin.flush()
                deadline=time.monotonic()+4*3600+180
                last=None
                while not (folder/'worker-done.json').exists():
                    if cancelled.is_set() or self.closed:
                        (folder/'cancel').touch();raise InterruptedError('用户取消，未发布部分输出')
                    if self.proc.poll() is not None:raise RuntimeError('计算进程意外退出，请查看日志后重试')
                    if time.monotonic()>deadline:raise TimeoutError('计算超过4小时时限')
                    try:
                        progress=json.loads((folder/'progress.json').read_text(encoding='utf8'))
                        if progress!=last:messages.put(progress);last=progress
                    except (OSError,ValueError):pass
                    time.sleep(.04)
                receipt=json.loads((folder/'worker-done.json').read_text(encoding='utf8'))
                outcome=json.loads((folder/'outcome.json').read_text(encoding='utf8'))
                if outcome['status']!='SUCCESS':self.stop()
                return receipt
            except BaseException:
                self.stop();raise

    def close(self):
        self.closed=True
        with self.lock:self.stop()


class WarmEngines:
    def __init__(self, engine, home):
        self.workers={}
        if not (engine/'code/studio_service.py').is_file():return
        for stage in ('CP','FT','FT-shared'):
            worker=Worker(engine,home/'compute-workers',stage);self.workers[stage]=worker
            threading.Thread(target=worker.prewarm,daemon=True,name='prewarm-'+stage).start()

    def status(self):
        result={}
        for name,worker in self.workers.items():
            process=worker.proc
            alive=bool(process and process.poll() is None)
            result[name]='ready' if worker.ready and alive else 'warming' if alive else 'idle'
        return result

    def close(self):
        for worker in self.workers.values():worker.closed=True
        for worker in self.workers.values():worker.close()
