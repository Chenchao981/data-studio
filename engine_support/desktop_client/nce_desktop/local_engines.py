"""Pinned copies of existing engines and explicit supported local operations."""

from __future__ import annotations

import json
import shutil
import sys
import platform
from dataclasses import replace
from pathlib import Path

from .storage import digest, write_json

ROOT = Path(__file__).resolve().parents[2]


def paths():
    for folder in (ROOT, ROOT / "backend"):
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))


def install_engines(home: Path, cp: Path, ft: Path):
    home = home.resolve()
    prepare_dependencies(home)
    registry = home / "engines" / "registry.json"
    if registry.exists():
        return
    engines = {}
    for stage, source in (("CP", cp), ("FT", ft)):
        checksum = digest(source)
        target = home / "engines" / checksum / (stage + ".pyz")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if digest(target) != checksum:
            raise ValueError("计算工具复制校验失败")
        engines[stage] = {"path": str(target), "sha256": checksum}
    write_json(registry, {"schema": 1, "runtime": sys.executable, "engines": engines})


def config(home):
    paths()
    from local_agent.config import AgentConfig

    record = json.loads((home / "engines/registry.json").read_text(encoding="utf-8"))
    return AgentConfig(
        enable_personal_tools=True,
        work_root=home / "tasks",
        python_runtime=Path(record["runtime"]),
        cp_package=Path(record["engines"]["CP"]["path"]),
        cp_package_sha256=record["engines"]["CP"]["sha256"],
        ft_package=Path(record["engines"]["FT"]["path"]),
        ft_package_sha256=record["engines"]["FT"]["sha256"],
        max_output_bytes=8 * 1024**3,
        run_timeout_seconds=4 * 3600,
    )


def desktop_capability(tool):
    if tool.analysis_type == 'QUICK_PAT':
        names = {'HUAHONG':'华虹','JETECH':'佳泰','LION':'立昂微','GUOYU':'国宇 FRD',
                 'JIEQUN':'杰群','RIYUEXIN':'日月新','JIEMIN':'上海捷敏','DIANJI':'电基',
                 'RIYUEGUANG':'日月光','JIJIA':'集佳'}
        tool = replace(tool, display_name=names.get(tool.factory_code,tool.factory_code)+'PAT统计')
        if tool.test_stage == 'CP':
            tool = replace(tool, input_kind='directory-or-file')
    if tool.test_stage == 'FT' and tool.analysis_type == 'QUICK_CHART':
        return replace(tool, input_kind='directory', allowed_suffixes=(
            ('.xls', '.xlsx') if tool.factory_code == 'JIEMIN' else tool.allowed_suffixes))
    return tool


def capabilities(home):
    paths()
    from local_agent.personal_tools import list_capabilities

    result = list_capabilities(config(home))
    from .local_native import capabilities as native_capabilities

    result.extend(native_capabilities(config(home)))
    result = [desktop_capability(t) for t in result]
    operation_order = {
        "QUICK_CLEAN": 0,
        "QUICK_PAT": 1,
        "QUICK_CHART": 2,
        "QUICK_SYL_SBL": 3,
    }
    return sorted(
        result,
        key=lambda t: (t.test_stage, t.factory_code, operation_order[t.analysis_type]),
    )


def tool_by_code(home, code):
    tool = next((t for t in capabilities(home) if t.tool_code == code), None)
    if not tool or not tool.enabled:
        raise ValueError(tool.disabled_reason if tool else "本版本没有该分析流程")
    return tool


def input_help(tool):
    from .local_native import BY_CODE

    if tool.test_stage == 'CP' and tool.analysis_type == 'QUICK_PAT':
        hint = BY_CODE[tool.tool_code].help if tool.tool_code in BY_CODE else '选择本工厂原始CP测试数据文件、文件夹或受支持压缩包。'
        return hint+'；统一使用FT算法：线性分位数、IQR/1.35、中位数±6Sigma；不按Bin或IQR删值，参数/单位/规格/条件兼容后才合并。'

    if tool.tool_code in BY_CODE:
        return BY_CODE[tool.tool_code].help
    if tool.test_stage == "FT" and tool.analysis_type == "QUICK_CHART":
        return "选择DC/FT原始数据文件夹；生成本机散点图和箱体图。独立DVDS/RG图表与压缩包图表入口暂未接入。"
    if tool.analysis_type == "QUICK_SYL_SBL":
        return "选择一个工厂良率 Excel 文件（.xls/.xlsx）；沿用原SYL/SBL口径。"
    if tool.factory_code == "HUAHONG":
        return "本入口为华虹DCP/TXT原始数据；TD Excel请选择“TD 数据清洗”。"
    if tool.factory_code == "GUOYU":
        return "选择已支持的国宇FRD原始Excel；其他产品格式不自动推断。"
    return (
        "选择原始测试数据；清洗、PAT和图表均沿用已发布工具的固定参数。允许："
        + "、".join(tool.allowed_suffixes)
    )


def request_for(home, tool_code, source, title="", parent_id=None):
    if not str(source).strip():
        raise ValueError("请先选择本地输入文件或文件夹")
    tool = tool_by_code(home, tool_code)
    source_task = None
    source_paths = None
    if str(source).startswith("history://"):
        import re
        from .local_native import BY_CODE
        from .local_store import History

        source_task = str(source)[len("history://") :]
        if not re.fullmatch(r"[a-f0-9]{32}", source_task):
            raise ValueError("历史来源编号无效")
        spec = BY_CODE.get(tool_code)
        previous = History(home).get(source_task)
        if (
            not spec
            or spec.mode != "CLEANED_PAT"
            or previous["status"] != "SUCCESS"
            or previous["factory"] != tool.factory_code
            or previous["request"]["operation"] != "QUICK_CLEAN"
        ):
            raise ValueError("该历史不能作为所选操作的输入")
        parent_id = parent_id or source_task
        path = None
    else:
        from .local_native import BY_CODE

        source_paths = (
            [
                Path(p.strip().strip('"')).expanduser().resolve()
                for p in str(source).split(";")
                if p.strip()
            ]
            if tool.test_stage == "CP"
            else [Path(source).expanduser().resolve()]
        )
        if not source_paths:
            raise ValueError("请先选择本地输入文件或文件夹")
        if len(set(source_paths)) != len(source_paths):
            raise ValueError("请勿重复选择同一个输入文件")
        if len(source_paths) > 1:
            permitted = (
                set(tool.allowed_suffixes)
                if tool.test_stage == 'CP' and tool.analysis_type == 'QUICK_PAT' else
                {'.txt','.dcp','.zip','.7z','.7zip','.rar'}
                if tool_code=='LOCAL_CP_HUAHONG_CLEAN_V1' else
                {".xlsx"}
                if BY_CODE[tool_code].mode == "TD"
                and all(p.suffix.lower() == ".xlsx" for p in source_paths)
                else {".zip", ".7z", ".rar"}
            )
            if any(
                not p.is_file()
                or p.suffix.lower() not in permitted.intersection(tool.allowed_suffixes)
                for p in source_paths
            ):
                raise ValueError(
                    "多选仅支持当前格式的压缩包，或多个TD Excel；不要混选文件夹和文件。"
                )
        for item in source_paths:
            if (
                not item.exists()
                or item.is_relative_to(home)
                or home.is_relative_to(item)
            ):
                raise ValueError("输入不存在或与客户端历史库交叠")
        path = source_paths[0]
    if path is not None and not path.exists():
        raise ValueError("请选择存在的本地输入文件或文件夹")
    if (
        path is not None
        and path.is_file()
        and path.suffix.lower() not in tool.allowed_suffixes
    ):
        raise ValueError("此操作不支持所选文件后缀，请按输入提示选择")
    if path is not None and (path.is_relative_to(home) or home.is_relative_to(path)):
        raise ValueError("输入目录不能与客户端历史库交叠")
    if (
        path is not None
        and tool.input_kind == "file"
        and (not path.is_file() or path.suffix.lower() not in {".xls", ".xlsx"})
    ):
        raise ValueError("SYL/SBL必须选择一个良率Excel文件")
    if path is not None and tool.input_kind == "directory" and not path.is_dir():
        raise ValueError("此操作需要原始数据文件夹")
    if (
        tool.factory_code == "JIEQUN"
        and path is not None
        and tool.analysis_type == "QUICK_CLEAN"
        and path.is_dir()
        and path.name.upper() == "DC"
    ):
        if any(
            p.is_dir() and p.name.upper() in {"DVDS", "RG"}
            for p in path.parent.iterdir()
        ):
            raise ValueError(
                "DC旁还有DVDS/RG目录，请选择共同的产品父目录，以完整记录本次分析输入。"
            )
    cfg = config(home)
    return {
        "schema": 1,
        "stage": tool.test_stage,
        "factory": tool.factory_code,
        "tool_code": tool.tool_code,
        "title": title.strip() or tool.display_name,
        "operation": tool.analysis_type,
        "source": (
            "; ".join(str(p) for p in source_paths) if source_paths else str(source)
        ),
        "source_paths": [str(p) for p in source_paths] if source_paths else None,
        "source_task_id": source_task,
        "profile": "UNASSIGNED",
        "package_sha256": tool.package_sha256,
        "runtime": str(cfg.python_runtime),
        "runtime_version": platform.python_version(),
        "client_version": "0.2.1-local",
        "parameters": {
            "mode": "已发布工具固定参数",
            "input_contract": tool.input_contract_version,
            "output_contract": tool.output_contract_version,
        },
        "input_help": input_help(tool),
        "parent_id": parent_id,
    }


def prepare_dependencies(home):
    """Pin pure Python Excel readers/writers without enabling roaming site packages."""
    import importlib.util

    manifest = home / "runtime-packages" / "manifest.json"
    files = {}
    distributions = {}
    if manifest.exists():
        dependency_path(
            home
        )  # Never bless changed files while adding a missing module.
        files.update(json.loads(manifest.read_text(encoding="utf-8"))["files"])
        distributions.update(
            json.loads(manifest.read_text(encoding="utf-8")).get("distributions", {})
        )
    changed = False
    for module in ("xlsxwriter", "xlrd"):
        if any(name.startswith(module + "/") for name in files):
            continue
        spec = importlib.util.find_spec(module)
        if spec is None or spec.origin is None:
            raise ValueError(f"本机运行环境缺少{module}，请配置完整的本地测试环境。")
        source = Path(spec.origin).parent
        target = manifest.parent / module
        shutil.copytree(
            source,
            target,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            dirs_exist_ok=True,
        )
        files.update(
            {
                p.relative_to(manifest.parent).as_posix(): digest(p)
                for p in target.rglob("*")
                if p.is_file()
            }
        )
        changed = True
    if "py7zr" not in distributions:
        # Archive dependencies can include CPython extensions. Copy the installed
        # distribution for this exact interpreter; do not enable arbitrary user-site imports.
        from importlib.metadata import distribution
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name

        visited = set()

        def pin_distribution(name):
            key = canonicalize_name(name)
            if key in visited:
                return
            visited.add(key)
            dist = distribution(name)
            for requirement in dist.requires or []:
                requirement = Requirement(requirement)
                if requirement.marker is None or requirement.marker.evaluate(
                    {"extra": ""}
                ):
                    pin_distribution(requirement.name)
            for relative in dist.files or []:
                if (
                    ".." in relative.parts
                    or "__pycache__" in relative.parts
                    or relative.suffix == ".pyc"
                ):
                    continue
                target = (manifest.parent / relative).resolve()
                if not target.is_relative_to(manifest.parent.resolve()):
                    raise ValueError("本地依赖分发路径无效")
                source_file = Path(dist.locate_file(relative))
                if not source_file.is_file():
                    raise ValueError(f"本地依赖文件缺失：{relative}")
                checksum = digest(source_file)
                file_key = relative.as_posix()
                if file_key in files and files[file_key] != checksum:
                    raise ValueError("新增依赖与固定依赖冲突，请使用独立测试工作区")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_file, target)
                files[file_key] = checksum
            distributions[key] = dist.version

        pin_distribution("py7zr")
        changed = True
    if not changed:
        return
    write_json(
        manifest,
        {
            "schema": 3,
            "python": list(sys.version_info[:2]),
            "files": files,
            "distributions": distributions,
        },
    )


def dependency_path(home):
    folder = home / "runtime-packages"
    record = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if record["python"] != list(sys.version_info[:2]):
        raise ValueError("本地依赖与Python版本不匹配")
    for name, checksum in record["files"].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or digest(path) != checksum:
            raise ValueError("本地运行依赖已改变，请修复测试环境")
    return folder.resolve()
