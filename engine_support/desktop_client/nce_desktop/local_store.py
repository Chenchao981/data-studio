"""Durable, offline-only task history. No server identity or network access."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .storage import digest, write_json

TERMINAL = {"SUCCESS", "FAILED", "CANCELLED", "INTERRUPTED"}
ACTIVE = {"QUEUED", "RUNNING", "CANCELLING"}
LABELS = {
    "QUEUED": "等待开始",
    "RUNNING": "分析中",
    "CANCELLING": "正在停止",
    "SUCCESS": "成功",
    "FAILED": "失败",
    "CANCELLED": "已取消",
    "INTERRUPTED": "已中断",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_home():
    return Path(
        os.environ.get("PYMS_CLIENT_HOME")
        or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NCE" / "PYMSClient"
    ).resolve()


class History:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "history.sqlite3"
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise RuntimeError(
                    "本地历史库版本较新，请使用对应客户端版本；未修改历史库。"
                )
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                  id TEXT PRIMARY KEY, profile TEXT NOT NULL DEFAULT 'UNASSIGNED',
                  parent_id TEXT, stage TEXT NOT NULL, title TEXT NOT NULL,
                  tool_code TEXT NOT NULL, factory TEXT NOT NULL, status TEXT NOT NULL,
                  created TEXT NOT NULL, started TEXT, finished TEXT,
                  request TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
                  result TEXT, trashed INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS ix_tasks_history ON tasks(profile,trashed,created DESC,id);
                CREATE TABLE IF NOT EXISTS events (
                  seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                  at TEXT NOT NULL, message TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_events_task ON events(task_id,seq);
            """
            )
            columns = {r[1] for r in db.execute("PRAGMA table_info(tasks)")}
            if "identity_json" not in columns:
                db.execute(
                    "ALTER TABLE tasks ADD COLUMN identity_json TEXT NOT NULL DEFAULT '{}'"
                )
            db.execute("PRAGMA user_version=2")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def task_dir(self, task_id):
        if len(task_id) != 32 or any(c not in "0123456789abcdef" for c in task_id):
            raise ValueError("无效任务编号")
        return self.root / "tasks" / task_id

    def create(self, request, parent_id=None):
        task_id = uuid4().hex
        if parent_id:
            parent = self.get(parent_id)
            if parent["status"] not in TERMINAL:
                raise ValueError("原任务结束后才可重新分析")
        self.task_dir(task_id).mkdir(parents=True)
        with self.connect() as db:
            db.execute(
                """INSERT INTO tasks(id,parent_id,stage,title,tool_code,factory,status,created,request)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    task_id,
                    parent_id,
                    request["stage"],
                    request["title"],
                    request["tool_code"],
                    request["factory"],
                    "QUEUED",
                    now(),
                    json.dumps(request, ensure_ascii=False),
                ),
            )
            db.execute(
                "INSERT INTO events(task_id,at,message) VALUES(?,?,?)",
                (task_id, now(), "任务已建档；本机未归属，仅本地保存。"),
            )
        return task_id

    def get(self, task_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM tasks WHERE id=? AND profile='UNASSIGNED'", (task_id,)
            ).fetchone()
        if row is None:
            raise KeyError("本地任务不存在")
        row = dict(row)
        row["request"] = json.loads(row["request"])
        row["result"] = json.loads(row["result"]) if row["result"] else None
        return row

    def list(
        self, *, stage="", status="", query="", page=1, page_size=20, trashed=False
    ):
        where, args = ["profile='UNASSIGNED'", "trashed=?"], [int(trashed)]
        for key, value in (("stage", stage), ("status", status)):
            if value:
                where.append(key + "=?")
                args.append(value)
        if query:
            where.append(
                "(instr(lower(title),lower(?))>0 OR instr(lower(request),lower(?))>0 OR instr(lower(identity_json),lower(?))>0)"
            )
            args.extend([query, query, query])
        sql = " FROM tasks WHERE " + " AND ".join(where)
        with self.connect() as db:
            total = db.execute("SELECT count(*)" + sql, args).fetchone()[0]
            rows = db.execute(
                "SELECT id,stage,title,status,created,finished,error,parent_id,identity_json"
                + sql
                + " ORDER BY created DESC,id DESC LIMIT ? OFFSET ?",
                [*args, min(100, max(1, page_size)), max(0, page - 1) * page_size],
            ).fetchall()
        return [dict(row) for row in rows], total

    def event(self, task_id, message):
        with self.connect() as db:
            db.execute(
                "INSERT INTO events(task_id,at,message) VALUES(?,?,?)",
                (task_id, now(), message[-4000:]),
            )

    def events(self, task_id):
        self.get(task_id)
        with self.connect() as db:
            rows = db.execute(
                "SELECT at,message FROM events WHERE task_id=? ORDER BY seq DESC LIMIT 300",
                (task_id,),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def transition(self, task_id, status, *, error="", result=None):
        allowed = {
            "QUEUED": {"RUNNING", "CANCELLED", "INTERRUPTED"},
            "RUNNING": {"CANCELLING", "SUCCESS", "FAILED", "INTERRUPTED", "CANCELLED"},
            "CANCELLING": {"CANCELLED", "INTERRUPTED", "FAILED"},
        }
        with self.connect() as db:
            old = db.execute(
                "SELECT status FROM tasks WHERE id=?", (task_id,)
            ).fetchone()[0]
            if status not in allowed.get(old, set()):
                raise ValueError(f"不允许从 {old} 变更为 {status}")
            db.execute(
                """UPDATE tasks SET status=?, error=?, result=COALESCE(?,result),
                started=CASE WHEN ?='RUNNING' THEN ? ELSE started END,
                finished=CASE WHEN ? THEN ? ELSE finished END WHERE id=?""",
                (
                    status,
                    error[-8000:],
                    json.dumps(result, ensure_ascii=False) if result else None,
                    status,
                    now(),
                    status in TERMINAL,
                    now(),
                    task_id,
                ),
            )
            db.execute(
                "INSERT INTO events(task_id,at,message) VALUES(?,?,?)",
                (
                    task_id,
                    now(),
                    LABELS[status] + ("：" + error[-4000:] if error else ""),
                ),
            )
            if result:
                db.execute(
                    "UPDATE tasks SET identity_json=? WHERE id=?",
                    (
                        json.dumps(
                            result.get("business_identity", {}), ensure_ascii=False
                        ),
                        task_id,
                    ),
                )

    def set_trash(self, task_id, trashed):
        with self.connect() as db:
            row = db.execute(
                "SELECT status FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if not row or row[0] not in TERMINAL:
                raise ValueError("任务结束后才可移入回收站")
            db.execute("UPDATE tasks SET trashed=? WHERE id=?", (int(trashed), task_id))
            db.execute(
                "INSERT INTO events(task_id,at,message) VALUES(?,?,?)",
                (
                    task_id,
                    now(),
                    "移入本地回收站，结果文件保留" if trashed else "恢复本地记录",
                ),
            )

    def artifact_path(self, task_id, item, *, verify=True):
        result_dir = (self.task_dir(task_id) / "result").resolve()
        path = (result_dir / item["path"]).resolve()
        if not path.is_relative_to(result_dir) or path.is_symlink():
            raise ValueError("结果路径无效")
        if not path.is_file():
            raise ValueError("本地附件缺失；历史仍保留。请查找备份或重新分析。")
        if path.stat().st_size != item["size"] or (
            verify and digest(path) != item["sha256"]
        ):
            raise ValueError("本地附件已改变；不会作为原始分析结果打开或导出。")
        return path

    def recover(self):
        """Caller must own the workspace OS lock; never infer by recycled PID."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,status FROM tasks WHERE status IN ('RUNNING','CANCELLING')"
            ).fetchall()
        for row in rows:
            task_id = row["id"]
            receipt_path = self.task_dir(task_id) / "result" / "completion.json"
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if receipt["task_id"] != task_id or row["status"] == "CANCELLING":
                    raise ValueError("任务未完成")
                if not receipt["artifacts"]:
                    raise ValueError("无结果")
                for item in receipt["artifacts"]:
                    self.artifact_path(task_id, item)
                self.transition(task_id, "SUCCESS", result=receipt)
                self.event(task_id, "重启核验已落盘结果后恢复成功记录，未重新计算。")
            except (OSError, ValueError, KeyError):
                self.transition(
                    task_id,
                    "INTERRUPTED",
                    error="上次程序异常结束；未自动重算，可用原参数新建任务。",
                )

    def export(self, task_id, parent: Path):
        row = self.get(task_id)
        if row["status"] != "SUCCESS" or not row["result"]:
            raise ValueError("仅成功任务可导出结果")
        parent = parent.expanduser().resolve()
        if parent.is_relative_to(self.root):
            raise ValueError("请将导出目录放在受管历史库之外")
        source = Path(row["request"]["source"]).resolve()
        if source.is_dir() and (
            parent.is_relative_to(source) or source.is_relative_to(parent)
        ):
            raise ValueError("导出目录不能与原始输入目录交叠")
        paths = [
            (item, self.artifact_path(task_id, item))
            for item in row["result"]["artifacts"]
        ]
        destination = parent / (
            "PYMS_" + row["stage"] + "_" + task_id[:8] + "_" + uuid4().hex[:8]
        )
        destination.mkdir(parents=True, exist_ok=False)
        for item, path in paths:
            target = destination / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        write_json(
            destination / "任务说明.json",
            {
                "task_id": task_id,
                "title": row["title"],
                "created": row["created"],
                "finished": row["finished"],
                "result": row["result"],
            },
        )
        self.event(task_id, "已导出独立副本；历史库中的原结果不变。")
        return destination
