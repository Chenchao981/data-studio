"""Lossless sheet preview. No generic worksheet is treated as measurement rows."""
from __future__ import annotations
import csv
import gzip
import io
import json
import sqlite3
from pathlib import Path, PurePosixPath
import zipfile
import hashlib


def index_artifacts(folder, artifacts):
    import openpyxl
    folder = Path(folder)
    target = folder/'preview.sqlite'
    tables = []
    direct={}
    for name,path in artifacts:
        if name.startswith('files/') and name.lower().endswith(('.csv','.csv.gz','.xlsx')):
            with Path(path).open('rb') as stream:direct[name[6:]]=hashlib.file_digest(stream,'sha256').hexdigest()
    con = sqlite3.connect(target)
    con.execute('CREATE TABLE cells(dataset TEXT,row_no INTEGER,data TEXT,search TEXT,PRIMARY KEY(dataset,row_no))')
    def add(label, rows):
        key = 't'+str(len(tables))
        count, width = 0, 0
        for row in rows:
            values = [v if isinstance(v,(str,int,float,bool)) or v is None else str(v) for v in row]
            import math
            values = [str(v) if isinstance(v,float) and not math.isfinite(v) else v for v in values]
            width=max(width,len(values));count+=1
            if count>2_000_000 or width>2048: raise ValueError('结果工作表超过预览容量')
            con.execute('INSERT INTO cells VALUES (?,?,?,?)',(key,count,json.dumps(values,ensure_ascii=False), '\t'.join(str(v) for v in values if v is not None).lower()))
        tables.append({'id':key,'name':label,'rows':count,'columns':width,'mode':'worksheet'})
    def read(name, stream):
        if name.lower().endswith('.xlsx'):
            book=openpyxl.load_workbook(stream,read_only=True,data_only=False)
            try:
                for sheet in book:
                    add(name+' / '+sheet.title, sheet.iter_rows(values_only=True))
            finally: book.close()
        elif name.lower().endswith(('.csv','.csv.gz')):
            binary=gzip.GzipFile(fileobj=stream,mode='rb') if name.lower().endswith('.gz') else stream
            add(name,csv.reader(io.TextIOWrapper(binary,encoding='utf-8-sig',errors='strict')))
    try:
        for name,path in artifacts:
            if Path(name).suffix.lower()=='.zip':
                with zipfile.ZipFile(path) as z:
                    total=0
                    for entry in z.infolist():
                        n=PurePosixPath(entry.filename)
                        if n.is_absolute() or '..' in n.parts or ':' in entry.filename:raise ValueError('输出压缩包含无效路径')
                        total+=entry.file_size
                        if total>8*1024**3:raise ValueError('输出解包超过上限')
                        if not entry.is_dir() and entry.filename.lower().endswith(('.csv','.csv.gz','.xlsx')):
                            with z.open(entry) as f:
                                # XLSX reader requires seeking; spool large members to disk.
                                import tempfile,shutil
                                with tempfile.SpooledTemporaryFile(max_size=16*1024**2) as spool:
                                    shutil.copyfileobj(f,spool);spool.seek(0)
                                    if entry.filename in direct:
                                        duplicate=hashlib.file_digest(spool,'sha256').hexdigest()==direct[entry.filename]
                                        spool.seek(0)
                                        if duplicate:continue
                                    read(entry.filename,spool)
            elif name.lower().endswith(('.csv','.csv.gz','.xlsx')):
                with Path(path).open('rb') as f:read(name,f)
        con.commit()
    finally:con.close()
    return tables


def preview(path, tables, params):
    table=next((t for t in tables if t['id']==params.get('dataset')),None)
    if not table:raise ValueError('请选择该任务的结果工作表')
    start,end=params.get('start',0),params.get('end',100)
    if type(start) is not int or type(end) is not int or not 0<=start<end<=start+200:raise ValueError('每次最多读取200行')
    search=params.get('search','')
    if not isinstance(search,str) or len(search)>200:raise ValueError('搜索条件过长')
    if params.get('sort') or params.get('filters'):raise ValueError('原表预览按原始行序显示；可搜索完整工作表')
    con=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        args=[table['id'],search.lower()]
        total=con.execute('SELECT count(*) FROM cells WHERE dataset=? AND instr(search,?)>0',args).fetchone()[0]
        rows=con.execute('SELECT row_no,data FROM cells WHERE dataset=? AND instr(search,?)>0 ORDER BY row_no LIMIT ? OFFSET ?',args+[end-start,start]).fetchall()
        return {'rows':[dict(_row=n,**{'c'+str(i):v for i,v in enumerate(json.loads(data))}) for n,data in rows],'total':total,'elapsedMs':0}
    finally:con.close()
