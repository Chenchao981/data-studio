"""One isolated job at a time; real engines and explicit demos share lifecycle rules."""
from __future__ import annotations

import csv
import hashlib
import multiprocessing as mp
import queue
import threading
import os
import time
from pathlib import Path

from .core import now


def simulate(task, folder, messages, cancelled):
    try:
        for progress in range(0, 100, 5):
            if cancelled.wait(.12):
                messages.put({"status": "CANCELLED", "error": "用户取消了模拟任务"})
                return
            messages.put({"progress": progress})
            if task["sourceId"] == "demo-fail" and progress == 30:
                raise ValueError("模拟格式冲突：该内置样本用于验证错误反馈和重试。请选其他示例验证成功流程。")
        root = Path(folder) / task["id"]
        root.mkdir(exist_ok=False)
        temp = root / "DEMO_result.csv.part"
        with temp.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["DEMO_ONLY", "row", "source_name", "value", "rule"])
            for i in range(100):
                writer.writerow(["NOT_PRODUCTION_DATA", i+1, task["name"], 600+(i%20), "demo.v1"])
        if cancelled.is_set():
            temp.unlink()
            messages.put({"status": "CANCELLED", "error": "用户取消了模拟任务"})
            return
        target = temp.with_suffix("")
        temp.rename(target)
        messages.put({"status": "SUCCESS", "progress": 100, "output": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    except BaseException as exc:
        messages.put({"status": "FAILED", "error": str(exc)})


class TaskManager:
    def __init__(self, core):
        self.core = core
        self.lock = threading.RLock()
        self.ctx = mp.get_context("spawn")
        self.waiting = []
        self.active = None
        self.job = None
        self.closed = False
        self.started_clock = None
        self.core.recover()

    def start(self, task_id):
        with self.lock:
            if self.closed:
                raise ValueError("客户端正在关闭")
            task = self.core.task(task_id)
            if task["status"] != "READY":
                raise ValueError("只有待运行任务可以进入队列；已结束任务请重新创建")
            if len(self.waiting) >= 100:
                raise ValueError("任务队列已满（100项）")
            task["status"] = "QUEUED"
            self.core.save_task(task)
            self.waiting.append(task_id)
            return True

    def cancel(self, task_id):
        with self.lock:
            task = self.core.task(task_id)
            if task["status"] not in {"READY", "QUEUED", "RUNNING"}:
                raise ValueError("已结束任务不能取消")
            if self.active and self.active[0] == task_id:
                self.active[3].set()
            else:
                if task_id in self.waiting:
                    self.waiting.remove(task_id)
                task.update(status="CANCELLED", error="用户取消了等待任务", finished=now())
                self.core.save_task(task)
            return True

    def tick(self):
        changed = False
        with self.lock:
            if self.closed:
                return False
            if self.active:
                task_id, process, messages, cancelled = self.active
                task = self.core.task(task_id)
                while True:
                    try:
                        item = messages.get_nowait()
                    except queue.Empty:
                        break
                    task.update(item)
                    if cancelled.is_set() and item.get('status') == 'SUCCESS' and not item.get('publishedDirectory'):
                        task.update(status='CANCELLED', output='', error='用户取消任务，未发布结果')
                    changed = True
                    if item.get("status"):
                        task["finished"] = now()
                        if self.started_clock is not None:
                            task["elapsedSeconds"] = round(time.monotonic()-self.started_clock, 3)
                if not process.is_alive():
                    process.join()
                    if task["status"] == "RUNNING":
                        task.update(status="CANCELLED" if cancelled.is_set() else "FAILED", error="计算进程已结束，未收到完整成功回执", finished=now())
                    messages.close()
                    process.close()
                    if self.job is not None:
                        self.job.Close()
                        self.job = None
                    self.active = None
                    changed = True
                if changed:
                    self.core.save_task(task)
            if not self.active and self.waiting:
                task_id = self.waiting.pop(0)
                task = self.core.task(task_id)
                messages, cancelled = self.ctx.Queue(), self.ctx.Event()
                ready = self.ctx.Event()
                process = self.ctx.Process(target=execute, args=(task, str(self.core.results), messages, cancelled, ready), daemon=True)
                try:
                    self.started_clock = time.monotonic()
                    process.start()
                    if os.name == "nt":
                        import win32api
                        import win32job
                        self.job = win32job.CreateJobObject(None, "")
                        limits = win32job.QueryInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation)
                        limits["BasicLimitInformation"]["LimitFlags"] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                        win32job.SetInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation, limits)
                        handle = win32api.OpenProcess(0x0100 | 0x0001, False, process.pid)
                        try:
                            win32job.AssignProcessToJobObject(self.job, handle)
                        finally:
                            handle.Close()
                    task.update(status="RUNNING", started=now())
                    self.active = (task_id, process, messages, cancelled)
                    ready.set()
                except Exception as exc:
                    if process.is_alive():
                        process.terminate()
                        process.join(2)
                    if self.job is not None:
                        self.job.Close()
                        self.job = None
                    task.update(status="FAILED", error=str(exc), finished=now())
                    messages.close()
                self.core.save_task(task)
                changed = True
        return changed

    def close(self):
        with self.lock:
            self.closed = True
            if self.active:
                task_id, process, messages, cancelled = self.active
                cancelled.set()
                process.join(2)
                if process.is_alive():
                    process.terminate()
                    process.join(2)
                task = self.core.task(task_id)
                if task["status"] == "RUNNING":
                    task.update(status="CANCELLED", error="退出客户端，未完成任务已停止", finished=now())
                    self.core.save_task(task)
                messages.close()
                process.close()
                if self.job is not None:
                    self.job.Close()
                    self.job = None
                self.active = None
            for task_id in self.waiting:
                task = self.core.task(task_id)
                task.update(status="CANCELLED", error="退出客户端，等待任务已取消；可重新执行", finished=now())
                self.core.save_task(task)
            self.waiting.clear()


def execute(task, folder, messages, cancelled, ready):
    if not ready.wait(30):return
    if task.get('demo'):
        simulate(task, folder, messages, cancelled)
    else:
        from .engine import run_real
        run_real(task, folder, messages, cancelled)
