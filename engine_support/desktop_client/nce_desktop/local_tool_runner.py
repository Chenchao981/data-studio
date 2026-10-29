"""Local-only extension: explicitly request native FT chart data from new engines."""

from pathlib import Path

from app.infrastructure.quick_tool_runner import QuickToolRunner
from app.infrastructure.child_process_environment import isolated_child_environment


class LocalToolRunner(QuickToolRunner):
    def _run_ft(self, *, analysis_type, release, source, work, results):
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
