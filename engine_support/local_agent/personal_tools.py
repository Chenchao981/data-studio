"""Run the same released CP/FT adapters locally, without server credentials."""
from __future__ import annotations

import sys
import time
import zipfile
from pathlib import Path

from .config import AgentConfig
from .errors import RunnerError
from .manifest import build_local_manifest, manifest_json
from .models import FT_JIEQUN_TOOL_CODE, ToolCapability, ToolRunResult
from .runner import FtJiequnQuickPatRunner, file_sha256, ft_jiequn_capability, cp_capability_gate


def _shared_contracts():
    # Source checkout and relocatable bundle both use the same app modules.
    backend = Path(__file__).resolve().parents[1] / "backend"
    if backend.is_dir() and str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from app.domain.quick_analysis import DIRECT_PATH_TOOL_CONTRACTS
    return DIRECT_PATH_TOOL_CONTRACTS


def supported_operations(contract: dict[str, object]) -> tuple[str, ...]:
    operations = ["CLEAN", "PAT"]
    if contract["test_stage"] == "CP" or contract["factory_code"] in {"JIEQUN", "RIYUEXIN", "DIANJI", "JIEMIN"}:
        operations.append("CHART")
    if contract["test_stage"] == "FT" and contract["factory_code"] in {"JIEQUN", "RIYUEXIN", "DIANJI"}:
        operations.append("SYL_SBL")
    return tuple(operations)


def split_tool_code(tool_code: str) -> tuple[str, str]:
    if "::" in tool_code:
        base, operation = tool_code.rsplit("::", 1)
    else:
        base, operation = tool_code, "PAT"
    contract = _shared_contracts().get(base)
    if not contract or operation not in supported_operations(contract):
        raise ValueError("unsupported local personal tool")
    return base, operation


def list_capabilities(config: AgentConfig) -> list[ToolCapability]:
    if not config.enable_personal_tools:
        return [ft_jiequn_capability(config), cp_capability_gate()]
    package_states = {}
    for stage, package, sha in (
        ("CP", config.cp_package, config.cp_package_sha256),
        ("FT", config.ft_package, config.ft_package_sha256),
    ):
        reason = None
        members: set[str] = set()
        if not package or not sha:
            reason = f"本机助手尚未安装已固定版本的 {stage} 工具"
        elif not package.is_file() or not config.python_runtime.is_file():
            reason = f"{stage} 工具或本机运行环境不可用，请重新安装本机助手"
        else:
            try:
                if file_sha256(package) != sha.lower():
                    reason = f"{stage} 工具文件发生变化，请使用完整的新版本助手"
                else:
                    with zipfile.ZipFile(package) as archive:
                        members = set(archive.namelist())
            except (OSError, zipfile.BadZipFile):
                reason = f"{stage} 工具发布包无法读取"
        package_states[stage] = (sha.lower() or None, reason, members)
    labels = {"HUAHONG": "华虹", "JETECH": "佳泰", "LION": "立昂微", "GUOYU": "国宇", "JIEQUN": "杰群", "RIYUEXIN": "日月新", "RIYUEGUANG": "日月光", "DIANJI": "电基", "JIJIA": "集佳", "JIEMIN": "上海捷敏"}
    names = {"CLEAN": "数据清洗", "PAT": "PAT 统计", "CHART": "图表分析", "SYL_SBL": "SBL / SYL"}
    result = []
    for base, contract in _shared_contracts().items():
        stage, factory = str(contract["test_stage"]), str(contract["factory_code"])
        sha, reason, members = package_states[stage]
        for operation in supported_operations(contract):
            required = {
                "HUAHONG": "clean_dcp_data.py", "JETECH": "jt_data_processor/jt_main_processor.py",
                "LION": "lion_batch_processor.py", "GUOYU": "guoyu_batch_processor.py",
                "RIYUEGUANG": "factories/tms_adapters/riyueguang_pat.py" if operation == "PAT" else "factories/tms_adapters/riyueguang_dc.py",
            }.get(factory, f"factories/{factory.lower()}/{'pat_cleaner' if operation == 'PAT' else 'dc_cleaner'}.py")
            unavailable = reason or (None if required in members else "本机发布包未包含当前功能，请更新完整工具包")
            if stage == "CP" and operation == "PAT" and "cp_data_processor/analysis/quick_pat.py" not in members:
                unavailable = unavailable or "本机 CP 发布包未提供 PAT 计算入口"
            code = base if base == FT_JIEQUN_TOOL_CODE and operation == "PAT" else f"{base}::{operation}"
            suffixes = (".xls", ".xlsx") if operation == "SYL_SBL" else tuple(dict.fromkeys((*contract["allowed_suffixes"], *contract.get("single_file_suffixes", ()))))
            result.append(ToolCapability(
                tool_code=code, display_name=f"{labels.get(factory, factory)} · {names[operation]}",
                test_stage=stage, factory_code=factory, analysis_type=f"QUICK_{operation}",
                input_contract_version=str(contract["input_contract_version"]),
                output_contract_version=str(contract["output_contract_version"]),
                entrypoint=str(contract["adapter_code"]), allowed_suffixes=suffixes,
                enabled=unavailable is None, disabled_reason=unavailable, package_sha256=sha,
                timeout_seconds=config.run_timeout_seconds, max_output_bytes=config.max_output_bytes,
                release_tool_code=base, receipt_contract="PYMS_LOCAL_TOOL_RESULT_V2",
                input_kind="file" if operation == "SYL_SBL" else "directory-or-file",
            ))
    return result


class PersonalToolRunner:
    def __init__(self, config: AgentConfig, *, engine=None):
        self.config = config
        self.engine = engine

    def run(self, *, tool: ToolCapability, source_path: Path, output_root: Path, expected_source_file_count: int) -> ToolRunResult:
        if not self.config.enable_personal_tools:
            return FtJiequnQuickPatRunner(self.config).run(tool=tool, source_path=source_path, output_root=output_root, expected_source_file_count=expected_source_file_count)
        current = next((item for item in list_capabilities(self.config) if item.tool_code == tool.tool_code), None)
        if not current or not current.enabled or current.package_sha256 != tool.package_sha256:
            raise RunnerError("LOCAL_TOOL_CHANGED", "本机工具已变化，请重新连接并选择工具", 409)
        base, operation = split_tool_code(tool.tool_code)
        contract = _shared_contracts()[base]
        from app.domain.cleaner_registry import CleanerRelease
        from app.infrastructure.quick_tool_runner import QuickToolRunner
        package = self.config.cp_package if tool.test_stage == "CP" else self.config.ft_package
        release = CleanerRelease(
            cleaner_release_id=0, format_profile_id=0, test_stage=tool.test_stage,
            factory_code=tool.factory_code, format_code=str(contract["format_code"]),
            profile_version="route-a-v1", cleaner_code=str(contract["cleaner_code"]),
            cleaner_version=f"sha256-{tool.package_sha256[:12]}", code_checksum=tool.package_sha256,
            artifact_uri=str(package), runtime_uri=str(self.config.python_runtime),
            entrypoint=tool.entrypoint, adapter_code=str(contract["adapter_code"]),
            input_contract_version=tool.input_contract_version, output_contract_version=tool.output_contract_version,
            execution_config_json=None, timeout_seconds=self.config.run_timeout_seconds,
            max_output_bytes=self.config.max_output_bytes,
        )
        manifest = build_local_manifest(source_path, allowed_suffixes=tool.allowed_suffixes, max_files=self.config.max_source_files)
        if manifest.file_count != expected_source_file_count:
            raise RunnerError("LOCAL_SOURCE_CHANGED", "所选文件清单已变化，请重新预览", 409)
        started = time.perf_counter()
        computed = (self.engine or QuickToolRunner()).run_release(
            analysis_type=tool.analysis_type, release=release, input_directory=source_path,
            output_root=output_root, source_manifest_json=manifest_json(manifest), source_manifest_sha256=manifest.sha256,
        )
        reports = [Path(item.path) for item in computed.artifacts if item.role in {"pat_report", "result_package"}]
        if len(reports) != 1:
            raise RunnerError("LOCAL_RESULT_CONTRACT_INVALID", "工具没有返回唯一的可下载结果", 422)
        return ToolRunResult(
            report_path=reports[0], parameter_count=computed.parameter_count if operation == "PAT" else None,
            record_count=computed.record_count, elapsed_seconds=round(time.perf_counter() - started, 3), stdout_tail=computed.stdout_tail,
        )
