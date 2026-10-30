from __future__ import annotations

import base64
import json
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from python_core.task_logs import read_task_log

from PySide6.QtCore import QObject, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog


class Bridge(QObject):
    response = Signal(str, str)
    changed = Signal()
    notification = Signal(str)
    imported = Signal(str)
    _finish = Signal(str, object, object)

    def __init__(self, core, tasks, parent, trusted):
        super().__init__(parent)
        self.core, self.tasks, self.window = core, tasks, parent
        self.trusted = trusted
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="studio-core")
        self.pending = set()
        self.actions = {}
        self.closed = False
        preferences=core.settings()
        self.last_input_directory = preferences['inputDirectory']
        from python_core.viewers import Viewers
        self.viewers=Viewers(core)
        self.last_output_directory=preferences['outputDirectory']
        self._finish.connect(self.complete)

    @Slot(str, object, object)
    def complete(self, request_id, value, error):
        self.pending.discard(request_id)
        if self.closed:
            return
        action=self.actions.pop(request_id,None)
        if action and not error:
            try:
                path=Path(value)
                if action=='openCPCharts':
                    value=QDesktopServices.openUrl(QUrl(value))
                elif action=='openOutputFolder':
                    value=QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
                elif action=='openArtifact':
                    if path.suffix.lower() not in {'.html','.xlsx','.csv','.zip','.json','.pdf'}:raise ValueError('此结果不能直接打开，请导出后查看')
                    value=QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
                else:
                    target,_=QFileDialog.getSaveFileName(self.window,'导出结果副本',str(Path.home()/'Desktop'/path.name),'结果文件 (*'+path.suffix+')')
                    if target:
                        dest=Path(target).resolve()
                        if dest.is_relative_to(self.core.root):raise ValueError('请选择工作区以外的位置')
                        for source in self.core.protected_sources():
                            if source['demo']:continue
                            original=Path(source['path']).resolve()
                            if dest==original or (source['folder'] and dest.is_relative_to(original)):raise ValueError('不能覆盖原始输入目录内的文件')
                        self.submit(request_id,lambda: (shutil.copy2(path,dest),True)[1])
                        return
                    value=False
            except Exception as exc:error=str(exc)
        if error:
            logging.warning("Bridge request failed: %s", error)
        self.response.emit(request_id, json.dumps({"ok": not bool(error), "value": value, "error": str(error) if error else ""}, ensure_ascii=False, allow_nan=False))

    def bootstrap(self):
        snapshot=self.core.bootstrap()
        snapshot['engines']['workers']=self.tasks.warm.status()
        return snapshot

    def submit(self, request_id, work):
        if len(self.pending) >= 32:
            raise ValueError("本地请求较多，请稍后重试")
        self.pending.add(request_id)
        future = self.pool.submit(work)
        def done(result):
            try:
                self._finish.emit(request_id, result.result(), None)
            except Exception as exc:
                if not self.closed:
                    self._finish.emit(request_id, None, str(exc))
        future.add_done_callback(done)

    def import_paths(self, paths):
        # Native selection/drop path; typed paths use explicit trusted RPCs below.
        if self.closed:
            return
        future = self.pool.submit(self.core.register, paths)
        def done(result):
            try:
                files = result.result()
                if self.closed:
                    return
                self.changed.emit()
                self.imported.emit(json.dumps([f['id'] for f in files]))
                self.notification.emit(f"已登记 {len(files)} 项本地输入；请选择工厂与操作后开始分析")
            except Exception as exc:
                if not self.closed:
                    self.notification.emit(str(exc))
        future.add_done_callback(done)

    @Slot(str, str, str)
    def request(self, request_id, method, payload):
        try:
            if self.closed or not self.trusted():
                raise ValueError("本地接口只对可信工作台开放")
            if len(request_id) > 64 or len(payload) > 12_000_000 or request_id in self.pending:
                raise ValueError("请求无效或过大")
            p = json.loads(payload)
            if not isinstance(p, dict):
                raise ValueError("请求参数必须为对象")
            if method == 'selectInputs':
                from .input_sources import select_input_sources
                preferences=self.core.settings()
                paths=select_input_sources(self.window,title='选择输入文件或文件夹',start_path=preferences['inputDirectory'])
                self.submit(request_id,lambda:self.core.register([str(p) for p in paths]))
            elif method == 'selectOutputDirectory':
                target=QFileDialog.getExistingDirectory(self.window,'选择清洗输出目录',self.core.settings()['outputDirectory'])
                if target:
                    self.last_output_directory=target
                    self.submit(request_id,lambda:self.core.set_output_directory(target))
                else:self.complete(request_id,False,None)
            elif method == "selectFiles":
                files, _ = QFileDialog.getOpenFileNames(self.window, "选择本地测试数据", self.last_input_directory, "测试数据 (*.xlsx *.xls *.csv *.txt *.dcp *.zip *.7z *.7zip *.rar);;所有文件 (*)")
                if files:self.last_input_directory=str(Path(files[0]).parent)
                self.submit(request_id, lambda: self.core.register(files))
            elif method == "selectFolder":
                folder = QFileDialog.getExistingDirectory(self.window, "选择本地文件夹", self.last_input_directory)
                if folder:self.last_input_directory=folder
                self.submit(request_id, lambda: self.core.register([folder] if folder else []))
            elif method == "exportChart":
                data = p.get("data", "")
                if not isinstance(data, str) or not data.startswith("data:image/png;base64,"):
                    raise ValueError("只接受PNG图表")
                binary = base64.b64decode(data.split(",", 1)[1], validate=True)
                if not binary.startswith(b"\x89PNG\r\n\x1a\n") or len(binary) > 8_000_000:
                    raise ValueError("图表无效或过大")
                target, _ = QFileDialog.getSaveFileName(self.window, "导出演示图表", str(Path.home() / "Desktop/DEMO_chart.png"), "PNG (*.png)")
                if target:
                    Path(target).write_bytes(binary)
                self.complete(request_id, bool(target), None)
            elif method == 'openArtifact':
                self.actions[request_id]=method
                self.submit(request_id,lambda:str(self.core.artifact(p.get('id'),p.get('index'))))
            elif method=='openCPCharts':
                self.actions[request_id]=method
                self.submit(request_id,lambda:self.viewers.open(p.get('id')))
            elif method=='getResultDetails':
                from python_core.results import details
                self.submit(request_id,lambda:details(self.core,p.get('id')))
            elif method=='exportResultFolder':
                from python_core.results import export_folder
                target=QFileDialog.getExistingDirectory(self.window,'保存原工具清洗文件夹',self.last_output_directory)
                if target:
                    self.last_output_directory=target
                    self.submit(request_id,lambda:export_folder(self.core,p.get('id'),target))
                else:self.complete(request_id,False,None)
            elif method=='openOutputFolder':
                from python_core.results import directory
                self.actions[request_id]=method
                self.submit(request_id,lambda:str(directory(self.core,p.get('id'))))
            elif method == "exportResult":
                self.actions[request_id]=method
                self.submit(request_id,lambda:str(self.core.output(p.get('id'))))
            elif method == "copyText":
                text = p.get("text")
                if not isinstance(text, str) or len(text) > 100000:
                    raise ValueError("复制内容过长")
                QApplication.clipboard().setText(text)
                self.complete(request_id, True, None)
            elif method == "openLogs":
                self.complete(request_id, QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.core.root / "logs"))), None)
            else:
                operations = {
                    "bootstrap": self.bootstrap,
                    "identifyFiles": self.core.workspace_files,
                    "applyInputPaths": lambda: self.core.apply_input_paths(p.get('text')),
                    "applyOutputPath": lambda: self.core.apply_output_path(p.get('text')),
                    "removeInputs": lambda: self.core.remove_inputs(p.get("ids")),
                    "createTask": lambda: self.core.create_task(p.get("sourceId"),p.get('toolCode'),p.get('sourceIds')),
                    "createFollowup": lambda: self.core.followup(p.get('id')),
                    "startTask": lambda: self.tasks.start(p.get("id")),
                    "cancelTask": lambda: self.tasks.cancel(p.get("id")),
                    "getTaskLog": lambda: read_task_log(self.core, p.get("id"), p.get("source", ""), p.get("offset", 0)),
                    "getTaskStatus": lambda: self.core.task(p.get("id")),
                    "getPreview": lambda: self.core.real_preview(p) if p.get('taskId') else self.core.preview(p),
                    "getChartData": lambda: self.core.chart(p.get("parameter"), p.get("lot", "")),
                    "listHistory": lambda: self.core.history(p.get("search", ""),p.get('stage',''),p.get('status',''),real_only=True),
                    "saveSettings": lambda: self.core.save_settings(p),
                    "clearCache": self.core.clear_cache,
                }
                if method not in operations:
                    raise ValueError("不支持的本地操作")
                self.submit(request_id, operations[method])
        except Exception as exc:
            self.complete(request_id, None, str(exc))

    def close(self):
        self.closed = True
        self.viewers.close()
        self.pool.shutdown(wait=True, cancel_futures=True)
