"""Lifecycle-owned, loopback-only original CP Cockpit for verified history results."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from urllib.request import build_opener, ProxyHandler
from uuid import uuid4
import zipfile

from .local_engines import config, dependency_path
from .local_process import ProcessTree
from .local_results import copy_dataset
from .storage import digest


class Viewers:
    def __init__(self, history, extra_paths=(), runtime=None):
        self.history = history
        self.extra_paths=tuple(extra_paths)
        self.runtime=runtime
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cp-viewer")
        self.lock = threading.Lock()
        self.closed = False
        self.sessions = []
        self.opened = {}

    def open(self, task_id):
        return self.pool.submit(self.start, task_id)

    def start(self, task_id):
        cfg = config(self.history.root)
        if self.runtime is not None:
            from dataclasses import replace
            cfg=replace(cfg,python_runtime=Path(self.runtime))
        row = self.history.get(task_id)
        if row["stage"] != "CP" or row["request"]["operation"] != "QUICK_CLEAN":
            raise ValueError("CP交互图表需要一条成功的CP清洗历史")
        if digest(cfg.cp_package) != row["request"]["package_sha256"]:
            raise ValueError("此历史的计算版本与当前图表工具不一致")
        primary = next(item for item in row["result"]["artifacts"] if item["primary"])
        self.history.artifact_path(task_id, primary)
        with self.lock:
            if self.closed:
                raise ValueError("客户端已退出")
            previous = self.opened.get(task_id)
            if previous and previous[0].poll() is None:
                return previous[1]
        workspace = self.history.root / "viewers" / uuid4().hex
        data = copy_dataset(self.history, task_id, workspace / "data")
        engine = workspace / "engine"
        engine.mkdir()
        with zipfile.ZipFile(cfg.cp_package) as archive:
            for info in archive.infolist():
                if not info.filename.endswith(".py"):
                    continue
                target = (engine / info.filename).resolve()
                if not target.is_relative_to(engine.resolve()):
                    raise ValueError("图表包路径无效")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
        script = engine / "frontend/cp_dashboard_app.py"
        if not script.is_file() or not list(data.rglob("*cleaned*.csv")):
            raise ValueError("历史缺少标准CP数据或图表入口")
        if self.extra_paths:
            # Newer Streamlit widgets treat even an unchanged session-state
            # assignment as a replacement value. Keep the original filter
            # validation, but only assign when the selection actually changes.
            # Adapt this disposable viewer copy; the pinned CP package remains
            # unchanged, including every data and chart calculation.
            old = "        st.session_state[key] = valid or option_list[:1]"
            new = "        next_values = valid or option_list[:1]\n        if list(current) != next_values:\n            st.session_state[key] = next_values"
            source = script.read_text(encoding='utf8')
            if source.count(old) != 1:
                raise ValueError('此CP图表版本需要更新控件兼容适配')
            script.write_text(source.replace(old,new),encoding='utf8')
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        from app.infrastructure.child_process_environment import (
            isolated_child_environment,
        )

        env = isolated_child_environment(
            {
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONPATH": os.pathsep.join(
                    [str(engine), *map(str,self.extra_paths), str(dependency_path(self.history.root))]
                ),
                "CP_COCKPIT_DATA_DIR": str(data),
                "CP_DATA_ROOT": str(workspace / "cp-data"),
                "CP_LOG_DIR": str(workspace / "cp-data/logs"),
                "CP_CONFIG_DIR": str(workspace / "cp-data/config"),
                "MPLCONFIGDIR": str(workspace / "matplotlib"),
            }
        )
        gate = workspace / "go"
        log = (workspace / "viewer.log").open("wb")
        try:
            process = subprocess.Popen(
                [
                    str(cfg.python_runtime),
                    str(Path(__file__).with_name("local_viewer_worker.py")),
                    str(gate),
                    str(script),
                    str(port),
                ],
                cwd=workspace,
                env=env,
                stdout=log,
                stderr=log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            tree = ProcessTree(process)
        finally:
            log.close()
        with self.lock:
            if self.closed:
                tree.close()
                raise ValueError("客户端已退出")
            self.sessions.append((process, tree))
            gate.touch()
        url = f"http://127.0.0.1:{port}"
        opener = build_opener(ProxyHandler({}))
        try:
            for _ in range(100):
                if self.closed or process.poll() is not None:
                    raise RuntimeError(
                        "本机图表服务未启动，请检查 " + str(workspace / "viewer.log")
                    )
                try:
                    with opener.open(url + "/_stcore/health", timeout=0.5) as response:
                        if response.status == 200:
                            with self.lock:
                                if self.closed:
                                    raise ValueError("客户端已退出")
                                self.opened[task_id] = (process, url)
                            self.history.event(
                                task_id, "打开本机CP交互图表，使用已校验结果副本。"
                            )
                            return url
                except OSError:
                    time.sleep(0.2)
            raise RuntimeError("本机图表启动超时")
        except Exception:
            tree.close()
            raise

    def close(self):
        with self.lock:
            self.closed = True
            for process, tree in self.sessions:
                tree.close()
        self.pool.shutdown(wait=True, cancel_futures=True)
