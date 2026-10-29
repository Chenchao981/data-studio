"""User-facing original files, separate from immutable task transport archives."""
from pathlib import Path, PurePosixPath
from datetime import datetime
import csv
import hashlib
import os
import re
import shutil


def original_files(core, task_id):
    task=core.task(task_id)
    if task['status']!='SUCCESS' or task.get('demo'):raise ValueError('请选择成功的真实清洗记录')
    files=[]
    for index,item in enumerate(task.get('artifacts',[])):
        if item['name'].startswith('files/'):
            files.append((item['name'][6:],core.artifact(task_id,index),item['sha256']))
    if not files:raise ValueError('此记录没有独立清洗文件，请使用完整归档ZIP')
    return task,files


def directory(core, task_id):
    task=core.task(task_id)
    saved=task.get('publishedDirectory')
    if saved and Path(saved).is_dir():return Path(saved)
    if not any(i['name'].startswith('files/') for i in task.get('artifacts',[])):
        return core.output(task_id).parent
    _,files=original_files(core,task_id)
    return Path(os.path.commonpath([str(p.parent) for _,p,_ in files]))


def details(core, task_id):
    # Opening history must not read spreadsheets, hash output files, or unpack
    # archives. Content verification stays on explicit open/export actions.
    task=core.task(task_id)
    if task['status']!='SUCCESS' or task.get('demo'):raise ValueError('请选择成功的真实清洗记录')
    files=[a for a in task.get('artifacts',[]) if a['name'].startswith('files/')]
    root=(core.results/task_id).resolve()
    paths=[Path(a['path']).resolve() for a in files]
    if any(not p.is_relative_to(root) for p in paths):raise ValueError('结果路径无效')
    saved=task.get('publishedDirectory')
    if saved and Path(saved).is_dir():folder=Path(saved)
    elif paths:folder=Path(os.path.commonpath([str(p.parent) for p in paths]))
    else:
        output=Path(task['output']).resolve()
        if not output.is_relative_to(root):raise ValueError('结果路径无效')
        folder=output.parent
    return {'directory':str(folder),'files':[a['name'][6:] for a in files]}


def export_folder(core, task_id, parent):
    task,files=original_files(core,task_id)
    parent=Path(parent).resolve(strict=True)
    if not parent.is_dir() or parent.is_relative_to(core.root):raise ValueError('请选择工作区以外的输出文件夹')
    for source in core.protected_sources():
        if not source['demo'] and source['folder'] and parent.is_relative_to(Path(source['path']).resolve()):raise ValueError('不能保存到原始输入目录内')
    # Copy from verified historical artifacts, even if a saved desktop copy was
    # edited, moved or deleted later.
    common=Path(os.path.commonpath([str(p.parent) for _,p,_ in files]))
    name=common.name
    if name=='files':
        cleaned=next((p for _,p,_ in files if '_cleaned_' in p.name and p.suffix.lower()=='.csv'),None)
        lot='清洗结果'
        if cleaned:
            with cleaned.open(encoding='utf-8-sig',newline='') as stream:lot=next(csv.DictReader(stream),{}).get('Lot_ID') or lot
        name=lot+'_'+datetime.fromisoformat(task['finished']).astimezone().strftime('%Y%m%d_%H%M%S')
    name=re.sub(r'[<>:"/\\|?*]','_',name).strip(' .') or '清洗结果'
    for number in range(1,10001):
        target=parent/(name if number==1 else name+'_'+str(number))
        try:target.mkdir();break
        except FileExistsError:continue
    else:raise ValueError('同名结果过多，请选择其他目录')
    try:
        for _,path,checksum in files:
            dest=target/path.relative_to(common)
            if not dest.resolve().is_relative_to(target.resolve()):raise ValueError('结果路径无效')
            dest.parent.mkdir(parents=True,exist_ok=True)
            with path.open('rb') as source,dest.open('xb') as output:shutil.copyfileobj(source,output)
            with dest.open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=checksum:raise ValueError('结果复制校验失败')
    except Exception:
        # Leave a visible marker; never report a partial export as complete.
        (target/'导出未完成.txt').write_text('本次导出失败，请重新导出完整结果。',encoding='utf8')
        raise
    return str(target)
