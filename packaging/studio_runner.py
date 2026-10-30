"""External CPython worker. Reuses the verified offline controller unchanged."""
from __future__ import annotations
import hashlib,json,sys,time,zipfile,shutil
from pathlib import Path
from nce_desktop.local_controller import Controller
from nce_desktop.local_engines import bind_bundle_engines
from nce_desktop.local_store import History,TERMINAL


def write_json(path, value):
    # Windows readers and antivirus can briefly hold a target without delete sharing.
    # Reuse one temporary file and retry atomic publication instead of failing analysis.
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.pending')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    for attempt in range(50):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 49: raise
            time.sleep(.02)

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def progress(folder, phase, value):
    # Progress is advisory. File contention must never change a business result.
    try:
        write_json(folder/'progress.json', {'phase': phase, 'progress': value})
    except OSError:
        print(phase, flush=True)


def main(folder):
    task=json.loads((folder/'request.json').read_text(encoding='utf8'))
    bundle=Path(__file__).resolve().parent.parent
    manifest=json.loads((bundle/'manifest.json').read_text(encoding='utf8'))
    import platform,importlib.metadata
    if platform.python_version()!=manifest['python']:raise ValueError('Python version differs from pinned engine')
    for name,version in manifest['packages'].items():
        if importlib.metadata.version(name)!=version:raise ValueError('Dependency version changed: '+name)
    spec=next(t for t in manifest['tools'] if t['tool_code']==task['toolCode'])
    home=folder/'engine-work'
    print('正在准备固定计算组件…',flush=True)
    bind_bundle_engines(home,bundle,manifest,spec['profile'])
    history=History(home);controller=Controller(history)
    try:
        originals={}
        if task.get('parentTask'):
            from nce_desktop.local_results import copy_dataset
            parent=task['parentTask']
            source=str(copy_dataset(History(Path(parent['folder'])/'engine-work'),parent['nativeId'],folder/'input-from-history'))
        elif spec['test_stage']=='FT' and (len(task['sourcePaths'])>1 or (spec['input_kind']=='directory' and Path(task['sourcePaths'][0]).is_file())):
            sources=list(map(Path,task['sourcePaths']))
            if any(not p.is_file() for p in sources):raise ValueError('多个FT输入必须是同类型文件，不能混选目录')
            label=sources[0].parent.name if sources[0].parent.name.upper() in {'DC','DVDS','RG'} else 'selected-inputs'
            copied=folder/'input-selection'/label;copied.mkdir(parents=True)
            for p in sources:
                dest=copied/p.name
                if dest.exists():raise ValueError('选择的文件重名，不能合并：'+p.name)
                originals[str(p)]=digest(p);shutil.copyfile(p,dest)
                if digest(dest)!=originals[str(p)]:raise ValueError('复制期间输入改变')
            source=str(copied)
        else:
            source=task['sourcePaths'][0] if len(task['sourcePaths'])==1 else '; '.join(task['sourcePaths'])
        native=controller.submit(task['toolCode'],source,task['name'])
        progress(folder,'原工具正在计算 · 进度以完成状态为准',20)
        while history.get(native)['status'] not in TERMINAL:
            if (folder/'cancel').exists():controller.cancel(native)
            time.sleep(.3)
        row=history.get(native)
        if row['status']!='SUCCESS':raise ValueError(row['error'] or '计算已中断')
        artifacts=[(a['path'],history.artifact_path(native,a)) for a in row['result']['artifacts']]
        progress(folder,'整理原始结果文件',90)
        if any(digest(Path(p))!=h for p,h in originals.items()):raise ValueError('分析期间原始输入改变，未发布结果')
        receipt={'schema':1,'tool':spec,'runtime':sys.version,'result':row['result'],'request':row['request'],'parentTask':task.get('parentTask'),'selectedOriginals':originals,'inputFingerprint':json.loads((home/'tasks'/native/'input-fingerprint.json').read_text(encoding='utf8'))}
        receipt_path=folder/'receipt.json';write_json(receipt_path,receipt)
        archive=folder/'analysis-result.zip'
        with zipfile.ZipFile(archive.with_suffix('.zip.part'),'x',zipfile.ZIP_DEFLATED) as z:
            for name,path in artifacts:z.write(path,'outputs/'+name,compress_type=zipfile.ZIP_STORED if path.suffix.lower() in {'.xlsx','.zip','.png','.jpg'} else zipfile.ZIP_DEFLATED)
            z.write(receipt_path,'receipt.json')
        archive.with_suffix('.zip.part').rename(archive)
        if (folder/'cancel').exists():raise ValueError('用户取消，未发布结果')
        followup='LOCAL_FT_'+spec['factory_code']+'_CLEANED_PAT_V1'
        if spec['analysis_type']!='QUICK_CLEAN' or not any(t['tool_code']==followup and t['enabled'] for t in manifest['tools']):followup=None
        output={'status':'SUCCESS','progress':100,'phase':'已完成','nativeId':native,'followupCode':followup,'output':str(archive),'sha256':digest(archive),'tables':[],'previewHash':'', 'warning':'','receipt':{'files':row['result'].get('source_files'),'records':row['result'].get('record_count'),'package':row['result']['package_sha256'],'factory':row['factory'],'stage':row['stage']},'artifacts':[{'name':name,'path':str(path),'sha256':digest(path)} for name,path in artifacts]}
        write_json(folder/'outcome.json',output)
    except BaseException as exc:write_json(folder/'outcome.json',{'status':'FAILED','error':str(exc)})
    finally:controller.shutdown()

if __name__=='__main__':main(Path(sys.argv[1]))
