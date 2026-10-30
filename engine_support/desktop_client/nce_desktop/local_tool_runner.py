"""Local-only extension: explicitly request native FT chart data from new engines."""

from pathlib import Path

from app.infrastructure.quick_tool_runner import QuickToolRunner
from app.infrastructure.child_process_environment import isolated_child_environment


class LocalToolRunner(QuickToolRunner):
    def __init__(self, *, process_runner=None, reuse_process=False):
        if process_runner is None:
            import subprocess
            process_runner=subprocess.run
        super().__init__(process_runner=process_runner)
        self.reuse_process=reuse_process

    def _run_ft(self, *, analysis_type, release, source, work, results):
        if self.reuse_process and analysis_type=='QUICK_CLEAN' and release.factory_code=='RIYUEGUANG':
            # Execute the exact approved shared-package script in its dedicated
            # warm process. CP/native FT are never imported into this process.
            import contextlib,os,subprocess,sys,traceback
            from collections import deque
            from app.infrastructure.quick_tool_runner import _FT_PERSONAL_TOOL_SCRIPT
            class Tail:
                def __init__(self,stream):self.stream=stream;self.parts=deque(maxlen=100)
                def write(self,text):self.parts.append(text[-8000:]);return self.stream.write(text)
                def flush(self):self.stream.flush()
                def value(self):return ''.join(self.parts)[-8000:]
            def inline(args,**kwargs):
                if args!=[str(Path(sys.executable).resolve()),'-c',_FT_PERSONAL_TOOL_SCRIPT] or not sys.flags.no_user_site:
                    raise ValueError('共享清洗只能在固定独立进程执行')
                old=os.environ.copy();out,err=Tail(sys.stdout),Tail(sys.stderr);code=0
                try:
                    os.environ.update(kwargs['env'])
                    with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
                        try:exec(_FT_PERSONAL_TOOL_SCRIPT,{'__name__':'__main__'})
                        except SystemExit as exc:
                            if exc.code:code=1;print(str(exc),file=sys.stderr)
                        except Exception:code=1;traceback.print_exc()
                finally:os.environ.clear();os.environ.update(old)
                return subprocess.CompletedProcess(args,code,out.value(),err.value())
            original=self._process_runner;self._process_runner=inline
            try:return super()._run_ft(analysis_type=analysis_type,release=release,source=source,work=work,results=results)
            finally:self._process_runner=original
        if analysis_type != "QUICK_CHART":
            return super()._run_ft(
                analysis_type=analysis_type,
                release=release,
                source=source,
                work=work,
                results=results,
            )
        if not source.is_dir():
            raise ValueError("FT图表入口要求选择原始数据文件夹")
        done = self._process_runner(
            [
                str(release.runtime_uri),
                str(Path(__file__).with_name("local_ft_charts.py")),
                str(release.artifact_uri),
                release.factory_code,
                str(source),
                str(work),
                str(results),
            ],
            env=isolated_child_environment(
                {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
            ),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=release.timeout_seconds,
        )
        if done.returncode:
            raise RuntimeError(
                "FT图表生成失败：" + (done.stderr or done.stdout)[-4000:]
            )
        files = sorted(
            p.relative_to(results).as_posix() for p in results.rglob("*") if p.is_file()
        )
        if not any(p.endswith(".png") for p in files):
            raise ValueError("FT未生成参数图片")
        count = None
        for line in done.stdout.splitlines():
            if line.startswith("PYMS_RECORD_COUNT="):
                count = int(line.split("=", 1)[1])
        return files, count
