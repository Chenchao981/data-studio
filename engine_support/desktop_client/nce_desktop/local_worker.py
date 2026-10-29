"""One immutable task per process; calls existing engines, never web APIs."""

from __future__ import annotations

import hashlib
import codecs
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

from .local_engines import config, paths, tool_by_code, dependency_path
from .storage import digest, write_json


class Cancelled(Exception):
    pass


class Interrupted(Exception):
    pass


def cancelled(task_dir):
    if (task_dir / "cancel").exists():
        raise Cancelled("用户在安全检查点取消任务。")


def source_fingerprint(source, tool, task_dir):
    from local_agent.manifest import build_local_manifest

    if isinstance(source, list):
        from types import SimpleNamespace

        files = []
        size, count = 0, 0
        for index, path in enumerate(source):
            manifest, rows = source_fingerprint(path, tool, task_dir)
            size += manifest.total_bytes
            count += manifest.file_count
            files.extend(
                dict(item, source_index=index, source=str(path)) for item in rows
            )
        if count > 100_000:
            raise ValueError("输入文件总数超过100,000")
        return SimpleNamespace(file_count=count, total_bytes=size), files

    manifest = build_local_manifest(
        source, allowed_suffixes=tool.allowed_suffixes, max_files=100_000
    )
    files = []
    for item in manifest.files:
        cancelled(task_dir)
        file = source / item.relative_path if source.is_dir() else source
        before = file.stat()
        hasher = hashlib.sha256()
        with file.open("rb") as stream:
            while block := stream.read(4 * 1024 * 1024):
                cancelled(task_dir)
                hasher.update(block)
        after = file.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("预检过程中输入文件发生变化，请停止修改后重试。")
        files.append(
            {
                "path": item.relative_path,
                "size": after.st_size,
                "mtime_ns": after.st_mtime_ns,
                "sha256": hasher.hexdigest(),
            }
        )
    return manifest, files


def process_runner(task_dir, dependencies=None):
    def run(args, **kwargs):
        cancelled(task_dir)
        timeout = kwargs.pop("timeout", 4 * 3600)
        kwargs.pop("capture_output", None)
        kwargs.pop("check", None)
        # Incidental engine logs must stay in this task, never beside its package.
        kwargs["cwd"] = str(task_dir)
        if dependencies:
            kwargs["env"] = dict(
                kwargs.get("env", os.environ), PYTHONPATH=str(dependencies)
            )
        kwargs["env"] = dict(
            kwargs.get("env", os.environ),
            PYTHONUNBUFFERED="1",
            CP_DATA_ROOT=str(task_dir / "cp-data"),
            CP_LOG_DIR=str(task_dir / "cp-data" / "logs"),
            CP_CONFIG_DIR=str(task_dir / "cp-data" / "config"),
            MPLCONFIGDIR=str(task_dir / "matplotlib"),
        )
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with tempfile.TemporaryDirectory(
            prefix="engine-log-", dir=task_dir
        ) as temporary, ExitStack() as stack:
            out_path, err_path = (
                Path(temporary) / "stdout.log",
                Path(temporary) / "stderr.log",
            )
            stdout = stack.enter_context(out_path.open("wb"))
            stderr = stack.enter_context(err_path.open("wb"))
            readers = [
                stack.enter_context(out_path.open("rb")),
                stack.enter_context(err_path.open("rb")),
            ]
            decoders = [
                codecs.getincrementaldecoder("utf-8")(errors="replace") for _ in readers
            ]

            def forward(final=False):
                # Distinct file handles: reading must not seek the child's write pointer.
                for reader, decoder in zip(readers, decoders):
                    text = decoder.decode(reader.read(), final=final)
                    if text:
                        print(text, end="", flush=True)

            proc = subprocess.Popen(args, stdout=stdout, stderr=stderr, **kwargs)
            start = time.monotonic()
            try:
                while proc.poll() is None:
                    if (task_dir / "cancel").exists():
                        proc.kill()
                        proc.wait()
                        raise Interrupted("计算进程已停止；部分输出不作为完成结果。")
                    if time.monotonic() - start > timeout:
                        proc.kill()
                        proc.wait()
                        raise Interrupted(
                            "本机计算超过时限，已停止；可检查输入后新建任务。"
                        )
                    forward()
                    time.sleep(0.2)
                forward(final=True)
                out = out_path.read_text(encoding="utf-8", errors="replace")
                err = err_path.read_text(encoding="utf-8", errors="replace")
                return subprocess.CompletedProcess(args, proc.returncode, out, err)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

    return run


def execute(home, task_id):
    paths()
    task_dir = home / "tasks" / task_id
    # Parent attaches us to a kill-on-close job before releasing this gate.
    deadline = time.monotonic() + 30
    while not (task_dir / "go").exists():
        if time.monotonic() > deadline:
            return 2
        time.sleep(0.05)
    request = json.loads((task_dir / "request.json").read_text(encoding="utf-8"))
    try:
        print("正在校验工具版本和原始文件…", flush=True)
        tool = tool_by_code(home, request["tool_code"])
        if tool.package_sha256 != request["package_sha256"]:
            raise ValueError("任务创建后的计算版本已改变，请重新确认后新建任务。")
        if request.get("source_task_id"):
            from .local_results import copy_dataset
            from .local_store import History

            source = copy_dataset(
                History(home),
                request["source_task_id"],
                task_dir / "input-from-history",
            )
        else:
            source = (
                [Path(p) for p in request["source_paths"]]
                if len(request.get("source_paths") or []) > 1
                else Path(request["source"])
            )
        manifest, before = source_fingerprint(source, tool, task_dir)
        write_json(task_dir / "input-fingerprint.json", before)
        cancelled(task_dir)
        from local_agent.personal_tools import PersonalToolRunner
        from .local_tool_runner import LocalToolRunner

        print(f"输入文件 {manifest.file_count} 个，开始本机计算。", flush=True)
        stage = task_dir / "staging"
        engine = LocalToolRunner(
            process_runner=process_runner(task_dir, dependency_path(home))
        )
        from .local_native import BY_CODE, run_native

        if tool.tool_code in BY_CODE:
            result = run_native(
                config(home),
                tool,
                source,
                stage,
                process_runner(task_dir, dependency_path(home)),
            )
        else:
            result = PersonalToolRunner(config(home), engine=engine).run(
                tool=tool,
                source_path=source,
                output_root=stage,
                expected_source_file_count=manifest.file_count,
            )
        print("计算结束，正在核对输入未变化及结果完整性…", flush=True)
        _, after = source_fingerprint(source, tool, task_dir)
        if before != after:
            raise ValueError(
                "计算期间原始输入发生变化；结果未登记为成功，请用稳定输入重试。"
            )
        cancelled(task_dir)
        artifacts = []
        for file in sorted(stage.rglob("*")):
            if not file.is_file():
                continue
            if file.is_symlink() or not file.resolve().is_relative_to(stage.resolve()):
                raise ValueError("输出含不受支持的链接")
            artifacts.append(
                {
                    "path": file.relative_to(stage).as_posix(),
                    "size": file.stat().st_size,
                    "sha256": digest(file),
                    "primary": file.resolve() == result.report_path.resolve(),
                }
            )
        if not artifacts or not any(a["primary"] for a in artifacts):
            raise ValueError("计算未生成可读取的主结果")
        identity = {}
        if tool.analysis_type == "QUICK_CLEAN":
            from .local_summary import clean_summary

            identity = clean_summary(result.report_path, tool.test_stage)
        cancelled(task_dir)
        receipt = {
            "schema": 1,
            "task_id": task_id,
            "artifacts": artifacts,
            "package_sha256": tool.package_sha256,
            "source_files": manifest.file_count,
            "source_bytes": manifest.total_bytes,
            "record_count": result.record_count,
            "parameter_count": result.parameter_count,
            "elapsed_seconds": result.elapsed_seconds,
            "input_fingerprint": before,
            "business_identity": identity,
        }
        write_json(stage / "completion.json", receipt)
        # A completion receipt moves with its files; History.recover can finish DB publication.
        os.replace(stage, task_dir / "result")
        write_json(task_dir / "outcome.json", {"status": "SUCCESS", "result": receipt})
        print("本地分析成功，结果和历史已保存；本版本不进行网络同步。", flush=True)
        return 0
    except Exception as exc:
        import traceback

        traceback.print_exc()
        state = (
            "CANCELLED"
            if isinstance(exc, Cancelled)
            else "INTERRUPTED" if isinstance(exc, Interrupted) else "FAILED"
        )
        message = str(exc)[-8000:]
        write_json(task_dir / "outcome.json", {"status": state, "error": message})
        print(message, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(execute(Path(sys.argv[1]).resolve(), sys.argv[2]))
