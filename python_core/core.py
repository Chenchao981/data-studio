from __future__ import annotations

import json
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.3.3"
COLUMNS = {"id", "product", "lot", "wafer", "x", "y", "bv", "leakage", "bin"}
NUMERIC = {"id", "x", "y", "bv", "leakage", "bin"}
STATES = {"READY", "QUEUED", "RUNNING", "SUCCESS", "FAILED", "CANCELLED"}


def now():
    return datetime.now(timezone.utc).isoformat()


class Core:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.results = self.root / "results"
        self.results.mkdir(exist_ok=True)
        (self.root / "logs").mkdir(exist_ok=True)
        self.db = self.root / "history.sqlite"
        self.verified = {}
        with self.connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS sources_path ON sources(json_extract(data,'$.path'));
            """)
            for key, value in [("theme", "light")]:
                con.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (key, value))
            for i, (name, kind) in enumerate([("CP_Demo_Wafer_01.csv", "CP"), ("FT_Demo_Lot_02.csv", "FT"), ("CP_Demo_Error.csv", "CP")]):
                source = dict(id=["demo-cp", "demo-ft", "demo-fail"][i], name=name, path="内置生成数据 / 不对应真实生产文件", size=[8400000, 3200000, 1024][i], kind=kind, demo=True, folder=False)
                con.execute("INSERT OR IGNORE INTO sources VALUES (?,?)", (source["id"], json.dumps(source, ensure_ascii=False)))

    @contextmanager
    def connect(self, demo=False):
        con = sqlite3.connect(self.root / "demo.sqlite" if demo else self.db, timeout=15)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def files(self):
        with self.connect() as con:
            return [json.loads(r[0]) for r in con.execute("""SELECT data FROM sources
                WHERE json_extract(data,'$.demo')=1 OR rowid IN
                (SELECT rowid FROM sources WHERE json_extract(data,'$.demo')=0 ORDER BY rowid DESC LIMIT 1000)
                ORDER BY rowid""")]

    def registered_sources(self, ids):
        # Resolve registered IDs independently of the bounded recent-input UI.
        # Historical replay can still find old registrations without rescanning
        # the entire source list once per selected item.
        with self.connect() as con:
            rows=con.execute('SELECT id,data FROM sources WHERE id IN ('+','.join('?' for _ in ids)+')',ids)
            return {row['id']:json.loads(row['data']) for row in rows}

    def protected_sources(self):
        # Export protection must include old imports even when the work list is
        # empty or the registration history exceeds the old UI limit.
        with self.connect() as con:
            return [dict(path=r[0],folder=bool(r[1]),demo=False) for r in con.execute(
                "SELECT json_extract(data,'$.path'),json_extract(data,'$.folder') FROM sources WHERE json_extract(data,'$.demo')=0")]

    def register(self, paths):
        if not isinstance(paths, list) or len(paths) > 100:
            raise ValueError("每次最多登记100项输入")
        added = []
        with self.connect() as con:
            for value in paths:
                if not isinstance(value, str) or value.startswith(("\\\\", "//")):
                    raise ValueError("请选择本机文件或目录")
                path = Path(value).resolve(strict=True)
                if not path.is_file() and not path.is_dir():
                    raise ValueError("只接受普通文件和文件夹")
                row=con.execute("SELECT data FROM sources WHERE json_extract(data,'$.path')=?",(str(path),)).fetchone()
                previous=json.loads(row[0]) if row else None
                info = path.stat()
                source = dict(id=previous["id"] if previous else uuid.uuid4().hex, name=path.name, path=str(path), size=info.st_size if path.is_file() else 0, kind="UNKNOWN", demo=False, folder=path.is_dir(), modified=info.st_mtime_ns, fingerprintKind="path-size-mtime (not content hash)")
                con.execute("INSERT INTO sources VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (source["id"], json.dumps(source, ensure_ascii=False)))
                added.append(source)
            if added:
                first=Path(added[0]['path'])
                self._set_preference(con,'input_directory',str(first if first.is_dir() else first.parent))
                self._set_preference(con,'input_ids',json.dumps([f['id'] for f in added]))
        return added

    def workspace_files(self):
        ids=self.settings()['inputIds']
        sources=self.registered_sources(ids) if ids else {}
        return [sources[i] for i in ids if i in sources and not sources[i]['demo']]

    def reset_inputs(self):
        # Start each client window with an empty work list, preserving paths,
        # source registrations and task history for replay.
        with self.connect() as con:self._set_preference(con,'input_ids','[]')

    def remove_inputs(self, ids):
        if not isinstance(ids,list) or len(ids)>100 or any(not isinstance(i,str) or len(i)>64 for i in ids):
            raise ValueError('待分析输入选择无效')
        # Only edit the current list. Registrations remain available to history
        # and running jobs; no source file or result is ever deleted here.
        with self.connect() as con:
            row=con.execute("SELECT value FROM settings WHERE key='input_ids'").fetchone()
            current=json.loads(row[0]) if row else []
            remaining=[i for i in current if i not in ids]
            self._set_preference(con,'input_ids',json.dumps(remaining))
        return remaining

    @staticmethod
    def _set_preference(con,key,value):
        con.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))

    def set_output_directory(self,value):
        from .paths import output_parent
        path=output_parent(value,self.root)
        with self.connect() as con:self._set_preference(con,'output_directory',str(path))
        return str(path)

    def settings(self):
        from .paths import desktop_directory
        with self.connect() as con:values=dict(con.execute('SELECT key,value FROM settings'))
        desktop=desktop_directory()
        def directory(key):
            value=values.get(key,'')
            return value if value and Path(value).is_dir() else desktop
        ids=json.loads(values.get('input_ids','[]'))
        sources=self.registered_sources(ids) if ids else {}
        ids=[i for i in ids if i in sources and Path(sources[i]['path']).exists()]
        return dict(theme=values['theme'],output=str(self.results),concurrency=1,version=VERSION,
                    inputDirectory=directory('input_directory'),inputIds=ids,outputDirectory=values.get('output_directory') or desktop)

    def save_settings(self, params):
        if set(params) != {"theme"} or params["theme"] not in {"light", "dark"}:
            raise ValueError("当前只支持修改明暗主题")
        with self.connect() as con:
            con.execute("UPDATE settings SET value=? WHERE key='theme'", (params["theme"],))
        return self.settings()

    def history(self, search="", stage="", status="", real_only=False):
        if not isinstance(search, str) or len(search) > 200:
            raise ValueError("搜索文字过长")
        if stage not in {'','CP','FT'} or status not in STATES | {''}:
            raise ValueError('无效历史筛选')
        with self.connect() as con:
            rows = con.execute("""SELECT data FROM tasks WHERE
                instr(lower(coalesce(json_extract(data,'$.name'),'') || ' ' ||
                coalesce(json_extract(data,'$.parser'),'') || ' ' ||
                coalesce(json_extract(data,'$.sourceSnapshot.path'),'')),lower(?))>0
                AND (?='' OR coalesce(json_extract(data,'$.parameters.stage'),json_extract(data,'$.receipt.stage'),'')=?)
                AND (?='' OR json_extract(data,'$.status')=?)
                AND (?=0 OR coalesce(json_extract(data,'$.demo'),0)=0)
                ORDER BY rowid DESC LIMIT 100""", (search,stage,stage,status,status,int(real_only)))
            return [json.loads(r[0]) for r in rows]

    def task(self, task_id):
        if not isinstance(task_id, str) or len(task_id) > 64:
            raise ValueError("无效任务ID")
        with self.connect() as con:
            row = con.execute("SELECT data FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise ValueError("任务不存在")
        return json.loads(row[0])

    def create_task(self, source_id, tool_code=None, source_ids=None):
        if not isinstance(source_id,str):raise ValueError('输入未通过本地选择或拖放登记')
        source = self.registered_sources([source_id]).get(source_id)
        if not source:
            raise ValueError("输入未通过本地选择或拖放登记")
        task = dict(id=uuid.uuid4().hex, name=source["name"], sourceId=source_id, sourceSnapshot=source, status="READY", progress=0, created=now(), finished="", error="", output="", parser="demo.v1", demo=True, ruleVersion="synthetic-1", parameters={"mode": "simulation", "readsSourceContents": False})
        if not source['demo']:
            from .engine import catalog, configuration, digest
            state=catalog()
            spec=next((t for t in state['tools'] if t['tool_code']==tool_code and t['enabled']),None)
            if not spec:raise ValueError('请先选择可用的工厂与分析操作；真实文件不会作为演示任务运行')
            ids=source_ids or [source_id]
            if not isinstance(ids,list) or not 1<=len(ids)<=100 or len(set(ids))!=len(ids) or ids[0]!=source_id:raise ValueError('输入选择无效或超过100项')
            registered=self.registered_sources(ids)
            sources=[registered.get(i) for i in ids]
            if any(f is None or f['demo'] for f in sources):raise ValueError('只能分析已登记的真实输入')
            paths=[Path(f['path']).resolve(strict=True) for f in sources]
            if len(paths)>1 and any(p.is_dir() for p in paths):raise ValueError('合并分析只接受多个文件；多个文件夹请选择逐项批量执行')
            for path in paths:
                if path.is_relative_to(self.root) or self.root.is_relative_to(path):raise ValueError('输入不能与工作区重叠')
                if ';' in str(path):raise ValueError('当前原工具不支持路径中的分号，请换用不含分号的路径')
                if path.is_file() and path.suffix.lower() not in spec['allowed_suffixes']:raise ValueError('所选操作不支持此文件类型：'+path.name)
            from .paths import output_parent
            destination=output_parent(self.settings()['outputDirectory'],self.root,paths)
            engine,manifest=configuration()
            task.update(outputParent=str(destination),name=source['name']+(f' 等{len(paths)}项' if len(paths)>1 else ''),demo=False,toolCode=tool_code,sourceIds=ids,sourcePaths=list(map(str,paths)),parser=spec['display_name'],engineHash=digest(engine/'manifest.json'),ruleVersion=manifest['version'],parameters={'mode':'真实本地分析','stage':spec['test_stage'],'factory':spec['factory_code'],'operation':spec['analysis_type']},phase='等待开始')
        elif source_ids and len(source_ids)>1:
            raise ValueError('演示输入请逐项执行')
        self.save_task(task)
        return task

    def save_task(self, task):
        if task["status"] not in STATES:
            raise ValueError("无效任务状态")
        with self.connect() as con:
            con.execute("INSERT INTO tasks VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (task["id"], json.dumps(task, ensure_ascii=False)))

    def followup(self, task_id):
        from .engine import configuration,digest,catalog
        parent=self.task(task_id)
        self.output(task_id)
        code=parent.get('followupCode')
        tool=next((t for t in catalog()['tools'] if t['tool_code']==code and t['enabled']),None)
        if not tool or parent.get('demo') or not parent.get('nativeId'):raise ValueError('此清洗结果不支持继续生成PAT')
        engine,manifest=configuration()
        task=dict(id=uuid.uuid4().hex,name=parent['name']+' · 结果PAT',sourceId=parent['sourceId'],sourceSnapshot=parent['sourceSnapshot'],sourceIds=parent.get('sourceIds'),sourcePaths=parent.get('sourcePaths'),status='READY',progress=0,created=now(),finished='',error='',output='',parser=tool['display_name'],demo=False,toolCode=code,engineHash=digest(engine/'manifest.json'),ruleVersion=manifest['version'],parameters={'mode':'历史结果PAT'},parentTask={'id':task_id,'folder':str(self.results/task_id),'nativeId':parent['nativeId']},phase='等待开始')
        from .paths import output_parent
        task['outputParent']=str(output_parent(self.settings()['outputDirectory'],self.root,parent.get('sourcePaths',[])))
        self.save_task(task)
        return task

    def recover(self):
        with self.connect() as con:
            rows = [json.loads(r[0]) for r in con.execute("SELECT data FROM tasks WHERE json_extract(data,'$.status') IN ('QUEUED','RUNNING')")]
        for task in rows:
            task.update(status="CANCELLED", error="上次客户端非正常退出，未完成的任务已中断；可重新执行。", finished=now())
            self.save_task(task)

    def bootstrap(self):
        from .engine import catalog
        return dict(files=self.workspace_files(), tasks=self.history(real_only=True), settings=self.settings(), root=str(self.root), demoRows=0, engines=catalog())

    def real_preview(self, params):
        from .result_index import preview
        from .engine import digest
        task=self.task(params.get('taskId'))
        if task['status']!='SUCCESS' or task.get('demo'):raise ValueError('请选择成功的真实分析任务')
        path=self.results/task['id']/'preview.sqlite'
        stamp=(path.stat().st_size,path.stat().st_mtime_ns,task.get('previewHash'))
        if self.verified.get(str(path))!=stamp:
            if not task.get('previewHash') or digest(path)!=task['previewHash']:raise ValueError('预览缓存缺失或已改变；请打开原始结果查看')
            self.verified[str(path)]=stamp
        return preview(path,task.get('tables',[]),params)

    def artifact(self, task_id, index):
        from .engine import digest
        task=self.task(task_id)
        if task['status']!='SUCCESS' or type(index) is not int or not 0<=index<len(task.get('artifacts',[])):raise ValueError('结果不存在')
        item=task['artifacts'][index];path=Path(item['path']).resolve(strict=True)
        if not path.is_relative_to(self.results/task_id) or digest(path)!=item['sha256']:raise ValueError('结果已改变或路径无效')
        return path

    def ensure_demo(self):
        with self.connect(demo=True) as con:
            con.execute("CREATE TABLE IF NOT EXISTS demo(id INTEGER PRIMARY KEY,product TEXT,lot TEXT,wafer TEXT,x INTEGER,y INTEGER,bv REAL,leakage REAL,bin INTEGER)")
            if con.execute("SELECT count(*) FROM demo").fetchone()[0] == 100000:
                return
            con.execute("DELETE FROM demo")
            def rows():
                for i in range(1, 100001):
                    bv = round(600 + 14 * (math.sin(i * 1.73) + math.sin(i * .383) + math.sin(i * .131)), 5)
                    leak = round(.3 + .06 * (math.sin(i * 1.21) + math.sin(i * .193)), 6)
                    yield i, "DEMO-IGBT", f"DEMO-{1 + (i-1) % 4}", f"{1 + (i-1) % 25:02}", (i-1) % 160, (i-1)//160, bv, leak, 1 if bv >= 570 else 2
            con.executemany("INSERT INTO demo VALUES (?,?,?,?,?,?,?,?,?)", rows())
            con.execute("CREATE INDEX IF NOT EXISTS demo_lot ON demo(lot)")
            con.execute("CREATE INDEX IF NOT EXISTS demo_bv ON demo(bv)")

    def preview(self, params):
        start, end = params.get("start", 0), params.get("end", 100)
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= start + 200 or start > 100000:
            raise ValueError("预览请求必须为0起始的至多200行区间")
        if params.get("dataset") not in {"demo_raw", "demo_clean"}:
            raise ValueError("M0仅提供演示数据预览")
        search = params.get("search", "")
        if not isinstance(search, str) or len(search) > 200:
            raise ValueError("无效搜索条件")
        terms, values = [], []
        if search:
            terms.append("(instr(lower(product),lower(?))>0 OR instr(lower(lot),lower(?))>0 OR instr(wafer,?)>0)")
            values += [search] * 3
        filters = params.get("filters", {})
        if not isinstance(filters, dict) or len(filters) > 9:
            raise ValueError("无效列筛选")
        for col, spec in filters.items():
            if col not in COLUMNS or not isinstance(spec, dict):
                raise ValueError("筛选列无效")
            op = spec.get("type", "contains")
            value = spec.get("filter", "")
            if col in NUMERIC:
                if not isinstance(value, (float, int)) or not math.isfinite(value):
                    raise ValueError("请输入有限数字")
                operator = {"equals": "=", "notEqual": "!=", "lessThan": "<", "lessThanOrEqual": "<=", "greaterThan": ">", "greaterThanOrEqual": ">="}.get(op)
                if operator:
                    terms.append(f'"{col}" {operator} ?'); values.append(value)
                elif op == "inRange" and isinstance(spec.get("filterTo"), (int, float)) and math.isfinite(spec["filterTo"]):
                    terms.append(f'"{col}" BETWEEN ? AND ?'); values.extend([value, spec["filterTo"]])
                else:
                    raise ValueError("不支持的数字筛选")
            else:
                if not isinstance(value, str) or len(value) > 200:
                    raise ValueError("无效文本条件")
                if op in {"contains", "notContains"}:
                    terms.append(f'instr(lower("{col}"),lower(?)) {"=0" if op == "notContains" else ">0"}'); values.append(value)
                elif op in {"equals", "notEqual"}:
                    terms.append(f'lower("{col}") {"!=" if op == "notEqual" else "="} lower(?)'); values.append(value)
                elif op in {"startsWith", "endsWith"}:
                    terms.append(f'substr(lower("{col}"), {"1" if op == "startsWith" else "-length(?)"}{",length(?)" if op == "startsWith" else ""})=lower(?)'); values.extend([value, value])
                else:
                    raise ValueError("不支持的文本筛选")
        order = []
        sort = params.get("sort", [])
        if not isinstance(sort, list) or len(sort) > 9:
            raise ValueError("无效排序")
        for item in sort:
            if not isinstance(item, dict) or item.get("colId") not in COLUMNS or item.get("sort") not in {"asc", "desc"}:
                raise ValueError("无效排序字段")
            order.append(f'"{item["colId"]}" {item["sort"]}')
        order.append("id ASC")
        self.ensure_demo()
        began = time.perf_counter()
        where = " WHERE " + " AND ".join(terms) if terms else ""
        with self.connect(demo=True) as con:
            total = con.execute("SELECT count(*) FROM demo" + where, values).fetchone()[0]
            rows = con.execute("SELECT * FROM demo" + where + " ORDER BY " + ",".join(order) + " LIMIT ? OFFSET ?", values + [end-start, start])
            result = [dict(r) for r in rows]
        return dict(rows=result, total=total, elapsedMs=(time.perf_counter()-began)*1000)

    def chart(self, parameter, lot=""):
        if parameter not in {"bv", "leakage"} or lot not in {"", "DEMO-1", "DEMO-2", "DEMO-3", "DEMO-4"}:
            raise ValueError("无效参数或批次")
        self.ensure_demo()
        where = " WHERE lot=?" if lot else ""
        args = [lot] if lot else []
        with self.connect(demo=True) as con:
            count, mean, low, high = con.execute(f'SELECT count(*),avg({parameter}),min({parameter}),max({parameter}) FROM demo' + where, args).fetchone()
            width = (high-low)/24 or 1
            buckets = dict(con.execute(f'SELECT min(23,cast(({parameter}-?)/? AS INTEGER)),count(*) FROM demo' + where + ' GROUP BY 1', [low, width]+args).fetchall())
            # Window rank samples each filtered population, avoiding modulo/lot aliasing.
            step = max(1, math.ceil(count/2000))
            points = [list(r) for r in con.execute(f'SELECT id,{parameter} FROM (SELECT id,{parameter},row_number() OVER (ORDER BY id) AS rn FROM demo{where}) WHERE (rn-1)%?=0 LIMIT 2000', args+[step])]
        return dict(histogram=[dict(label=f"{low+i*width:.3f}", count=buckets.get(i, 0)) for i in range(24)], points=points, count=count, mean=mean, min=low, max=high, sampleCount=len(points), unit="V" if parameter == "bv" else "μA")

    def clear_cache(self):
        with self.connect(demo=True) as con:
            con.execute("DROP TABLE IF EXISTS demo")
        self.ensure_demo()
        return True

    def output(self, task_id):
        task = self.task(task_id)
        if task["status"] != "SUCCESS" or not task["output"]:
            raise ValueError("该任务没有可用的成功结果")
        path = Path(task["output"]).resolve(strict=True)
        if not path.is_relative_to(self.results / task["id"]) or not path.is_file():
            raise ValueError("结果路径无效")
        from .engine import digest
        if digest(path) != task.get("sha256"):
            raise ValueError("结果已改变，不能当作原结果导出")
        return path
