"""Desktop-only native operation contracts; never extend the server's API registry."""

from dataclasses import dataclass
from pathlib import Path
import zipfile

from .storage import digest


@dataclass(frozen=True)
class NativeOperation:
    stage: str
    factory: str
    mode: str
    name: str
    module: str
    suffixes: tuple[str, ...]
    help: str
    kind: str = "directory"

    @property
    def code(self):
        return f"LOCAL_{self.stage}_{self.factory}_{self.mode}_V1"

    @property
    def analysis(self):
        return "QUICK_PAT" if "PAT" in self.mode else "QUICK_CLEAN"


ARCHIVES = (".zip", ".7z", ".7zip", ".rar")
HH_PAT_CODE = "LOCAL_CP_HUAHONG_RAW_PAT_V1"
OPERATIONS = [
    NativeOperation(
        "CP", "HUAHONG", "RAW_PAT", "PAT（原始数据，FT口径）",
        "cp_data_processor/readers/dcp_reader.py", (".txt", ".dcp", *ARCHIVES),
        "选择华虹DCP/TXT、递归文件夹或ZIP/7z/RAR。按“NCE产品_批次@站号”识别；同一产品汇总计算并输出一个PAT Excel。公式与FT一致：IQR/1.35、中位数±6Sigma。",
        "directory-or-file",
    ),
    NativeOperation(
        "CP",
        "HUAHONG",
        "TD",
        "TD 数据清洗",
        "cp_data_processor/processing/hh_td_processor.py",
        (".xlsx", ".zip", ".7z"),
        "华虹TD：选择Excel、文件夹或ZIP/7z。按完整Lot+Wafer识别，保留片号前导零；Bin 1合格，其他Bin不良。完成后从历史打开统一CP图表。",
        "directory-or-file",
    ),
]

for factory, label, module, suffixes in [
    ("HUAHONG", "DCP / TXT", "clean_dcp_data.py", (".txt", ".dcp", ".zip", ".7z", ".7zip", ".rar")),
    (
        "JETECH",
        "佳泰",
        "jt_data_processor/jt_main_processor.py",
        (".xls", ".xlsx", ".zip"),
    ),
    ("LION", "立昂微", "lion_batch_processor.py", (".xls", ".xlsx", ".zip", ".rar")),
    ("GUOYU", "国宇FRD", "guoyu_batch_processor.py", (".xls", ".xlsx", ".zip")),
]:
    OPERATIONS.append(
        NativeOperation(
            "CP",
            factory,
            "CLEAN",
            label + " 数据清洗",
            module,
            suffixes,
            ("华虹DCP/TXT：支持文件、递归文件夹、ZIP/7z/7zip/RAR；散文件保留原批次目录，重复Lot+Wafer会停止。完成后打开清洗文件夹或统一CP图表。" if factory=='HUAHONG' else f"{label}：原工具清洗入口。选择数据目录，或多个同类型压缩包（{'、'.join(suffixes)}）；多个文件路径以分号分隔。完成后从历史打开统一CP交互图表。"),
            "directory-or-file",
        )
    )

for factory, label, mode, module, suffixes in [
    ("JIEQUN", "杰群", "DC", "dc_auto", (".csv",)),
    ("JIEQUN", "杰群", "DVDS", "dvds_cleaner", (".csv",)),
    ("JIEQUN", "杰群", "RG", "rg_cleaner", (".csv",)),
    ("RIYUEXIN", "日月新", "DC", "dc_cleaner", (".xls", ".xlsx")),
    ("RIYUEXIN", "日月新", "DVDS", "dvds_cleaner", (".xlsx",)),
    ("RIYUEXIN", "日月新", "RG", "rg_cleaner", (".xlsx",)),
    ("JIEMIN", "上海捷敏", "FT_ALL", "dc_cleaner", (".xls", ".xlsx")),
    ("JIEMIN", "上海捷敏", "DVDS", "dvds_cleaner", (".xls", ".xlsx")),
    ("JIEMIN", "上海捷敏", "RG", "rg_cleaner", (".csv", ".xls", ".xlsx")),
    ("DIANJI", "电基", "FT_ALL", "dc_cleaner", (".xls", ".xlsx", ".csv")),
    ("JIJIA", "集佳", "FT_ALL", "dc_cleaner", (".csv",)),
]:
    # Auxiliary cleaners in the released native GUI accept directories only.
    archive_enabled = mode in {"DC", "FT_ALL"} and factory != "JIEQUN"
    raw = suffixes + (ARCHIVES if archive_enabled else ())
    text = (
        "DC-AI（自动识别）"
        if factory == "JIEQUN" and mode == "DC"
        else "DC" if factory == "JIEMIN" and mode == "FT_ALL"
        else mode.replace("_", "-")
    )
    OPERATIONS.append(
        NativeOperation(
            "FT",
            factory,
            mode,
            text + " 数据清洗",
            f"factories/{factory.lower()}/{module}.py",
            raw,
            f"{label} {text}：选择原始数据文件夹（{'、'.join(raw)}）。沿用原工具专用入口；输出清洗Excel。",
        )
    )

for factory, suffixes in [
    ("JIEQUN", (".csv",)),
    ("RIYUEXIN", (".xls", ".xlsx")),
    ("JIEMIN", (".xls", ".xlsx")),
    ("DIANJI", (".xls", ".xlsx", ".csv")),
    ("JIJIA", (".csv",)),
]:
    OPERATIONS.append(
        NativeOperation(
            "FT",
            factory,
            "RAW_PAT",
            "PAT · 原始数据",
            f"factories/{factory.lower()}/pat_cleaner.py",
            suffixes + (ARCHIVES if factory in {"DIANJI", "JIJIA"} else ()),
            ("上海捷敏 PAT：选择 DC 原始 XLS/XLSX 文件或文件夹；沿用原工具动态参数、条件和规格口径，以原工具支持的原始格式为准，不用已清洗Excel替代。" if factory == "JIEMIN" else "选择原始测试数据文件夹；使用原工具generate_raw_pat。杰群、日月新可选择包含DC/DVDS/RG的产品父目录；不能用已清洗Excel替代原始输入。"),
        )
    )
    if factory in {"JIEQUN", "RIYUEXIN", "DIANJI"}:
        OPERATIONS.append(
            NativeOperation(
                "FT",
                factory,
                "CLEANED_PAT",
                "PAT · 已清洗Excel",
                f"factories/{factory.lower()}/pat_cleaner.py",
                (".xls", ".xlsx"),
                "选择原工具生成的清洗Excel所在文件夹（DC_Data / DVDS_Data / RG_Data等标准表）；使用原generate_pat，不重新解析原始文件。可在历史中选中清洗任务后点击“基于此结果分析”。",
            )
        )

BY_CODE = {operation.code: operation for operation in OPERATIONS}


def capabilities(cfg):
    from local_agent.models import ToolCapability

    result = []
    states = {}
    for stage, path, sha in [
        ("CP", cfg.cp_package, cfg.cp_package_sha256),
        ("FT", cfg.ft_package, cfg.ft_package_sha256),
    ]:
        try:
            if digest(path) != sha:
                raise ValueError("计算包校验失败")
            with zipfile.ZipFile(path) as archive:
                states[stage] = (set(archive.namelist()), None, sha)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            states[stage] = (set(), str(exc), sha)
    for spec in OPERATIONS:
        members, reason, sha = states[spec.stage]
        reason = reason or (
            None if spec.module in members else "固定计算包缺少此原生功能"
        )
        if spec.code == HH_PAT_CODE:
            ft_members, ft_reason, _ = states['FT']
            reason = reason or ft_reason or (None if {'shared/pat_engine.py', 'shared/excel_utils.py'} <= ft_members else '固定FT计算包缺少PAT统计组件')
        result.append(
            ToolCapability(
                tool_code=spec.code,
                display_name=spec.name,
                test_stage=spec.stage,
                factory_code=spec.factory,
                analysis_type=spec.analysis,
                input_contract_version=spec.code,
                output_contract_version="NATIVE_RESULT_V1",
                entrypoint=spec.module,
                allowed_suffixes=spec.suffixes,
                enabled=reason is None,
                disabled_reason=reason,
                package_sha256=sha,
                timeout_seconds=cfg.run_timeout_seconds,
                max_output_bytes=cfg.max_output_bytes,
                input_kind=spec.kind,
            )
        )
    return result


def visible(tool):
    """Keep legacy codes resolvable for old history, show native equivalents on new forms."""
    if tool.tool_code in BY_CODE:
        return True
    if tool.test_stage == 'CP' and tool.factory_code == 'HUAHONG' and tool.analysis_type == 'QUICK_PAT':
        return False
    if tool.test_stage == "CP" and tool.analysis_type == "QUICK_CLEAN":
        return False
    return not (
        tool.test_stage == "FT"
        and tool.factory_code in {"JIEQUN", "RIYUEXIN", "JIEMIN", "DIANJI", "JIJIA"}
        and tool.analysis_type in {"QUICK_CLEAN", "QUICK_PAT"}
    )


def run_native(cfg, tool, source, stage, runner):
    """Execute only the pinned engine in a separate interpreter, including CP/FT module isolation."""
    import json
    import time
    from local_agent.models import ToolRunResult
    from app.infrastructure.child_process_environment import isolated_child_environment

    start = time.perf_counter()
    stage.mkdir(parents=True)
    package = cfg.cp_package if tool.test_stage == "CP" else cfg.ft_package
    extra_env = {}
    if tool.test_stage == 'CP' and tool.analysis_type == 'QUICK_PAT':
        if digest(cfg.ft_package) != cfg.ft_package_sha256:
            raise ValueError('FT PAT计算包校验失败')
        extra_env = {'STUDIO_FT_PAT_PACKAGE': str(cfg.ft_package), 'STUDIO_FT_PAT_SHA256': cfg.ft_package_sha256}
    done = runner(
        [
            str(cfg.python_runtime),
            str(Path(__file__).with_name("local_native_worker.py")),
            str(package),
            tool.tool_code,
            json.dumps(
                [str(p) for p in source] if isinstance(source, list) else [str(source)]
            ),
            str(stage),
        ],
        env=isolated_child_environment(
            {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", **extra_env}
        ),
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=cfg.run_timeout_seconds,
    )
    if done.returncode:
        raise RuntimeError(
            "原工具执行失败：" + (done.stderr + "\n" + done.stdout)[-6000:]
        )
    info = json.loads((stage / "native-summary.json").read_text(encoding="utf-8"))
    files = [p for p in (stage / "files").rglob("*") if p.is_file()]
    if not files or any(
        p.is_symlink() or not p.resolve().is_relative_to(stage.resolve()) for p in files
    ):
        raise ValueError("原工具未生成有效结果")
    if sum(p.stat().st_size for p in files) > cfg.max_output_bytes:
        raise ValueError("结果超过本机输出上限")
    report = stage / "result.zip"
    with zipfile.ZipFile(report, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, file.relative_to(stage / "files"))
    if (
        sum(p.stat().st_size for p in stage.rglob("*") if p.is_file())
        > cfg.max_output_bytes
    ):
        raise ValueError("结果及打包文件超过本机输出上限")
    return ToolRunResult(
        report_path=report,
        record_count=info.get("record_count"),
        parameter_count=info.get("parameter_count"),
        elapsed_seconds=round(time.perf_counter() - start, 3),
        stdout_tail=done.stdout[-4000:],
    )
