"""Serial cleaning in fixed-runtime processes; CP/native FT/shared FT stay apart."""
from __future__ import annotations
import gc, importlib, json, logging, os, sys, tempfile, time, traceback
from pathlib import Path
from studio_runner import main, digest, write_json


def serve(worker, control):
    stage='CP' if worker=='CP' else 'FT'
    profile='shared' if worker=='FT-shared' else 'native'
    bundle=Path(__file__).resolve().parent.parent
    manifest_hash=digest(bundle/'manifest.json')
    manifest=json.loads((bundle/'manifest.json').read_text(encoding='utf8'))
    # The parent must own the Windows process tree before imports can spawn work.
    deadline=time.monotonic()+30
    while not (control/'go').exists():
        if time.monotonic()>deadline:raise TimeoutError('计算进程启动未授权')
        time.sleep(.02)
    for name,expected in manifest['files'].items():
        if name.startswith('runtime/') and '/' in name[len('runtime/'):]:continue
        path=(bundle/name).resolve()
        if not path.is_relative_to(bundle.resolve()) or digest(path)!=expected:
            raise ValueError('预热组件校验失败：'+name)
    package=bundle/'packages'/('cp.pyz' if stage=='CP' else profile+'.pyz')
    logging.basicConfig(level=logging.INFO,stream=sys.stdout,format='%(asctime)s · %(levelname)s · %(message)s',datefmt='%H:%M:%S')
    base_path=sys.path[:]
    sys.path[:0]=[str(package),str(bundle/'code/desktop_client/nce_desktop')]
    # Import only calculation entry modules; never create cleaners or read inputs.
    modules=({'factories.tms_adapters.riyueguang_dc'} if profile=='shared' else
             {t['entrypoint'].removesuffix('.py').replace('/','.') for t in manifest['tools']
              if t['profile']=='native' and t['analysis_type']=='QUICK_CLEAN' and t['test_stage']==stage and t['enabled']})
    for module in sorted(modules):importlib.import_module(module)
    import nce_desktop.local_worker, nce_desktop.local_native_worker
    # CP bundles legacy reader dependencies inside its PYZ. They belong to the
    # native dispatcher, not to the runtime-distribution verification namespace.
    sys.path[:]=base_path
    from nce_desktop.local_engines import bind_bundle_engines
    bind_bundle_engines(control/'bindings',bundle,manifest,profile)
    bindings={name:json.loads((control/'bindings'/name).read_text(encoding='utf8'))
              for name in ('runtime-packages/manifest.json','engines/registry.json')}
    idle_stdout,idle_stderr=os.dup(1),os.dup(2)
    write_json(control/'ready.json',{'pid':os.getpid(),'stage':stage,'profile':profile,'runtime':sys.executable,'engineHash':manifest_hash})
    for line in sys.stdin:
        command=json.loads(line)
        folder=Path(command['folder']).resolve()
        task=json.loads((folder/'request.json').read_text(encoding='utf8'))
        spec=next(t for t in manifest['tools'] if t['tool_code']==task['toolCode'])
        if command['engineHash']!=manifest_hash or digest(bundle/'manifest.json')!=manifest_hash:
            raise ValueError('预热后计算版本改变，必须重新启动计算进程')
        if spec['profile']!=profile or spec['analysis_type']!='QUICK_CLEAN' or spec['test_stage']!=stage or (profile=='shared' and spec['factory_code']!='RIYUEGUANG'):
            raise ValueError('任务不属于此计算进程')
        old_path=sys.path[:]
        old_temp=tempfile.tempdir
        try:
            # Redirect the OS handles as well as Python output, retaining live
            # logging handlers created by the original engines during warmup.
            sys.stdout.flush();sys.stderr.flush()
            with (folder/'execution.log').open('a',encoding='utf8') as log:
                os.dup2(log.fileno(),1);os.dup2(log.fileno(),2)
                os.chdir(folder)
                (folder/'temporary').mkdir()
                tempfile.tempdir=str(folder/'temporary')
                main(folder,persistent=True,bindings=bindings)
                gc.collect()
                sys.stdout.flush();sys.stderr.flush()
            outcome=json.loads((folder/'outcome.json').read_text(encoding='utf8'))
            write_json(folder/'worker-done.json',{'pid':os.getpid(),'stage':stage,'profile':profile,'runtime':sys.executable,'engineHash':manifest_hash})
            # Errors can leave original-library global state partially mutated.
            if outcome['status']!='SUCCESS':return
        except BaseException:
            traceback.print_exc();raise
        finally:
            sys.stdout.flush();sys.stderr.flush()
            os.dup2(idle_stdout,1);os.dup2(idle_stderr,2)
            sys.path[:]=old_path
            tempfile.tempdir=old_temp
            os.chdir(control)


if __name__=='__main__':serve(sys.argv[1],Path(sys.argv[2]).resolve())
