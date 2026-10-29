"""Serial background scheduler, leaving Qt and history browsing responsive."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .local_engines import ROOT, config, request_for
from .local_process import ProcessTree
from .local_store import History, TERMINAL
from .storage import write_json


class Controller:
    def __init__(self, history: History):
        self.history = history
        self.guard = threading.RLock()
        self.queue = []
        self.active = None
        self.stopping = False
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def submit(self, tool_code, source, title="", parent_id=None):
        with self.guard:
            if self.stopping:
                raise ValueError("程序正在关闭，不能新建任务")
            request = request_for(
                self.history.root, tool_code, source, title, parent_id
            )
            if shutil.disk_usage(self.history.root).free < 256 * 1024**2:
                raise ValueError(
                    "本地历史库可用空间不足256 MB，请释放磁盘空间后再分析。"
                )
            task_id = self.history.create(request, request.get("parent_id"))
            self.queue.append(task_id)
            return task_id

    def resume(self, task_id):
        with self.guard:
            if self.stopping or self.history.get(task_id)["status"] != "QUEUED":
                raise ValueError("只有等待开始的任务可继续")
            if task_id not in self.queue and task_id != self.active:
                self.queue.append(task_id)
                self.history.event(task_id, "用户恢复等待队列。")

    def cancel(self, task_id):
        with self.guard:
            row = self.history.get(task_id)
            if row["status"] == "QUEUED":
                self.queue = [t for t in self.queue if t != task_id]
                self.history.transition(task_id, "CANCELLED", error="在执行前取消")
            elif row["status"] == "RUNNING":
                self.history.transition(task_id, "CANCELLING")
                (self.history.task_dir(task_id) / "cancel").touch()

    def shutdown(self):
        with self.guard:
            self.stopping = True
            if self.active:
                self.cancel(self.active)
        self.thread.join(12)
        return not self.thread.is_alive()

    def _loop(self):
        while True:
            with self.guard:
                if self.stopping:
                    return
                task_id = self.queue.pop(0) if self.queue else None
                if task_id:
                    self.active = task_id
                    self.history.transition(task_id, "RUNNING")
            if not task_id:
                time.sleep(0.1)
                continue
            try:
                self._run(task_id)
            except Exception as exc:
                with self.guard:
                    if self.history.get(task_id)["status"] not in TERMINAL:
                        self.history.transition(task_id, "FAILED", error=str(exc))
            finally:
                with self.guard:
                    self.active = None

    def _run(self, task_id):
        folder = self.history.task_dir(task_id)
        request = self.history.get(task_id)["request"]
        write_json(folder / "request.json", request)
        env = {
            key: os.environ[key]
            for key in (
                "SystemRoot",
                "WINDIR",
                "COMSPEC",
                "TEMP",
                "TMP",
                "PATH",
                "PATHEXT",
                "NUMBER_OF_PROCESSORS",
                "LOCALAPPDATA",
                "APPDATA",
                "USERPROFILE",
                "HOMEDRIVE",
                "HOMEPATH",
                "ProgramFiles",
                "ProgramFiles(x86)",
                "ProgramW6432",
                "SystemDrive",
            )
            if key in os.environ
        }
        env.update(
            PYTHONUTF8="1",
            PYTHONIOENCODING="utf-8",
            NUMEXPR_MAX_THREADS="8",
            PYTHONPATH=os.pathsep.join(
                [str(ROOT / "desktop_client"), str(ROOT), str(ROOT / "backend")]
            ),
            CP_DATA_ROOT=str(folder / "cp-data"),
        )
        proc, tree = None, None
        try:
            with (folder / "execution.log").open("w", encoding="utf-8") as log:
                proc = subprocess.Popen(
                    [
                        str(config(self.history.root).python_runtime),
                        "-u",
                        "-m",
                        "nce_desktop.local_worker",
                        str(self.history.root),
                        task_id,
                    ],
                    cwd=folder,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    start_new_session=os.name != "nt",
                )
                tree = ProcessTree(proc)
                (folder / "go").touch()
                cancelling_since = None
                started = time.monotonic()
                while proc.poll() is None:
                    if (folder / "cancel").exists():
                        cancelling_since = cancelling_since or time.monotonic()
                        if time.monotonic() - cancelling_since > 5:
                            tree.close()
                            proc.wait(timeout=5)
                            break
                    if time.monotonic() - started > 4 * 3600 + 120:
                        tree.close()
                        proc.wait(timeout=5)
                        break
                    time.sleep(0.1)
            outcome_path = folder / "outcome.json"
            if not outcome_path.exists():
                # Finish a valid result rename even if the worker's final
                # notification was lost; otherwise retain an interrupted run.
                tree.close()
                with self.guard:
                    self.history.recover()
                return
            outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
            with self.guard:
                row = self.history.get(task_id)
                if row["status"] == "CANCELLING" and outcome["status"] == "SUCCESS":
                    outcome = {
                        "status": "INTERRUPTED",
                        "error": "停止请求与完成交叉；输出保留，未发布为成功。",
                    }
                self.history.transition(
                    task_id,
                    outcome["status"],
                    error=outcome.get("error", ""),
                    result=outcome.get("result"),
                )
        finally:
            if tree:
                tree.close()
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
