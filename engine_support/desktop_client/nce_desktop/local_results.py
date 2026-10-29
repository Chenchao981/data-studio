"""Materialize verified result copies, never run an analysis against the original receipt."""

from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile


def copy_dataset(history, task_id, destination):
    row = history.get(task_id)
    if row["status"] != "SUCCESS" or row["request"]["operation"] != "QUICK_CLEAN":
        raise ValueError("请选择已成功完成的清洗任务")
    primary = next(item for item in row["result"]["artifacts"] if item["primary"])
    source = history.artifact_path(task_id, primary)
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(source) as archive:
        total = 0
        seen = set()
        for info in archive.infolist():
            name = PurePosixPath(info.filename.replace("\\", "/"))
            target = (destination / name).resolve()
            if (
                name.is_absolute()
                or ".." in name.parts
                or ":" in str(name)
                or not target.is_relative_to(destination)
            ):
                raise ValueError("结果压缩包路径无效")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("结果包含链接")
            if info.is_dir():
                continue
            if name.suffix.lower() not in {".csv", ".xls", ".xlsx", ".json"}:
                continue
            key = str(name).casefold()
            if key in seen:
                raise ValueError("结果压缩包存在重复路径")
            seen.add(key)
            total += info.file_size
            if total > 8 * 1024**3 or len(seen) > 100_000:
                raise ValueError("结果解包超过本机上限")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as stream, target.open("xb") as output:
                shutil.copyfileobj(stream, output)
    if not seen:
        raise ValueError("该结果未包含可继续分析的标准数据")
    return destination
