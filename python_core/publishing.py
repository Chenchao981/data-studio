"""Save original reports to a user-selected parent after successful cleaning."""
import csv
import hashlib
import os
from pathlib import Path
import re
import shutil
from datetime import datetime
from uuid import uuid4
from .paths import output_parent


def publish(task,workspace,cancelled):
    parent=output_parent(task['outputParent'],workspace,task.get('sourcePaths',[]))
    managed=(Path(workspace)/'results'/task['id']).resolve()
    artifacts=task.get('artifacts',[])
    direct=[a for a in artifacts if a['name'].startswith('files/')]
    selected=direct or artifacts
    if not selected:raise ValueError('没有可保存的原工具输出')
    files=[]
    for item in selected:
        path=Path(item['path']).resolve(strict=True)
        if not path.is_relative_to(managed) or not path.is_file():raise ValueError('原结果路径无效')
        files.append((path,item['sha256']))
    common=Path(os.path.commonpath([str(p.parent) for p,_ in files]))
    name=common.name if direct else task.get('parameters',{}).get('factory','分析结果')
    if name=='files':
        cleaned=next((p for p,_ in files if '_cleaned_' in p.name and p.suffix.lower()=='.csv'),None)
        name=task.get('parameters',{}).get('factory','分析结果')
        if cleaned:
            with cleaned.open(encoding='utf-8-sig',newline='') as f:name=next(csv.DictReader(f),{}).get('Lot_ID') or name
    name=re.sub(r'[<>:"/\\|?*]','_',name).strip(' .') or '分析结果'
    if not re.search(r'_\d{8}_\d{6}(?:_\d+)?$',name):name+='_'+datetime.now().strftime('%Y%m%d_%H%M%S')
    pending=parent/('.studio-saving-'+uuid4().hex)
    pending.mkdir()
    published=[]
    try:
        for source,checksum in files:
            relative=source.relative_to(common);dest=pending/relative
            dest.parent.mkdir(parents=True,exist_ok=True)
            digest=hashlib.sha256()
            with source.open('rb') as reader,dest.open('xb') as writer:
                while chunk:=reader.read(1024*1024):
                    if cancelled.is_set():raise InterruptedError('已取消保存结果')
                    digest.update(chunk);writer.write(chunk)
            if digest.hexdigest()!=checksum:raise ValueError('原结果已改变，未发布输出')
            with dest.open('rb') as reader:
                if hashlib.file_digest(reader,'sha256').hexdigest()!=checksum:raise ValueError('输出复制校验失败')
            published.append({'name':relative.as_posix(),'sha256':checksum})
        for index in range(10000):
            if cancelled.is_set():raise InterruptedError('已取消保存结果')
            target=parent/(name if index==0 else name+f'_{index:03d}')
            if target.exists():continue
            try:pending.rename(target);break  # Windows rename never overwrites an existing folder.
            except FileExistsError:continue
        else:raise ValueError('输出同名目录过多，请选择其他位置')
        return {'publishedDirectory':str(target),'publishedFiles':published,'phase':'清洗完成，已保存到输出目录'}
    finally:
        if pending.exists():
            # Only remove our unique, incomplete staging directory under the
            # validated output parent. Never remove an existing result folder.
            resolved=pending.resolve()
            if resolved.parent==parent.resolve() and resolved.name.startswith('.studio-saving-'):
                shutil.rmtree(resolved)
