from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal

CleanerUseScope = Literal["FORMAL_IMPORT", "PERSONAL_ANALYSIS"]


@dataclass(frozen=True, slots=True)
class CleanerFormatMethod:
    """One independently maintained raw-format detector/parser method."""

    method_code: str
    display_name: str
    extensions: tuple[str, ...]
    detector_entrypoint: str
    parser_entrypoint: str
    fail_closed_notes: str


@dataclass(frozen=True, slots=True)
class CleanerCapability:
    """TMS-visible capability that binds a release contract to format methods."""

    capability_code: str
    display_name: str
    test_stage: str
    factory_code: str
    adapter_code: str
    cleaner_code: str
    input_contract_version: str
    output_contract_version: str
    use_scopes: tuple[CleanerUseScope, ...]
    format_method_codes: tuple[str, ...]
    format_code: str | None = None


FORMAT_METHODS: tuple[CleanerFormatMethod, ...] = (
    CleanerFormatMethod("HUAHONG_TD_EXCEL", "华虹 TD Excel（动态参数、DS及复测文件名）", (".xlsx",),
        "cp_data_processor.readers.hh_td_reader.HHTDReader",
        "cp_data_processor.processing.hh_td_processor.process_hh_td",
        "按参数名合并同Lot不同Wafer；重复Lot+Wafer及编号/单位/规格冲突拒绝；保留Bin和缺测，pass_bin=1"),
    CleanerFormatMethod("JIJIA_STS8203_CSV", "集佳 STS8203 CSV", (".csv",),
        "factories.jijia.parser.is_jijia_csv_file", "factories.jijia.parser.parse_jijia_file",
        "仅已验证产品、程序、字段及单位；不推断Bin合格含义"),
    CleanerFormatMethod("JIJIA_DTA_CSV", "集佳 NCEAP40P80G DTA CSV", (".csv",),
        "factories.jijia.parser.is_jijia_csv_file", "factories.jijia.dta_parser.parse_dta_file",
        "校验产品/程序/Quantity及全部Bias，缺测参数留空，拒绝混合格式"),
    CleanerFormatMethod("JIEMIN_PROFILED_XLS", "上海捷敏 DC 动态 PowerTECH XLS/XLSX、DVDS QA 完整报告/明细", (".xls", ".xlsx"),
        "factories.jiemin.parser.parse_jiemin_file", "factories.jiemin.parser.parse_jiemin_file",
        "动态参数按名称/条件/单位/次序对齐；QA故障留空、全记录保留；产品归一，缺批次用产品并提示；冲突拒绝"),
    CleanerFormatMethod("JIEMIN_RG_LCR", "上海捷敏 RG 双 DIE LCR CSV/Excel", (".csv", ".xls", ".xlsx"),
        "factories.jiemin.rg_parser.parse_jiemin_rg_file", "factories.jiemin.rg_parser.parse_jiemin_rg_file",
        "按内容验证CSV/BIFF/OOXML；四项Cs/Rs独立保留，F/ohm不换算；来源编号和业务批次分开"),
    CleanerFormatMethod(
        "HUAHONG_DCP_TEXT",
        "华虹 DCP 文本",
        (".txt",),
        "clean_dcp_data.process_directory",
        "clean_dcp_data.process_directory",
        "内容验证由正式工具执行；必须保留目录或压缩包内产品及批次身份",
    ),
    CleanerFormatMethod(
        "JETECH_CP_EXCEL",
        "佳泰 CP Excel",
        (".xls", ".xlsx"),
        "jt_data_processor.jt_main_processor.process_jt_files",
        "jt_data_processor.jt_main_processor.process_jt_files",
        "仅已验收工作簿布局，保留 Lot/Wafer 和 pass_bin=1",
    ),
    CleanerFormatMethod(
        "RIYUEXIN_DC_EXCEL",
        "日月新 DC Excel / XML XLS",
        (".xls", ".xlsx"),
        "factories.tms_adapters.riyuexin_dc.RiyuexinTmsDCCleaner",
        "factories.tms_adapters.riyuexin_dc.RiyuexinTmsDCCleaner",
        "沿用已验证NCT/ST完整批号及XML解析，递归扫描；来源/规格冲突拒绝，缺Lot进入补录，不推断PASS/FAIL",
    ),
    CleanerFormatMethod(
        "RIYUEGUANG_DC_EXCEL",
        "日月光 DC Excel",
        (".xlsx",),
        "factories.tms_adapters.riyueguang_dc.RiyueguangTmsDCCleaner",
        "factories.tms_adapters.riyueguang_dc.RiyueguangTmsDCCleaner",
        "正式 Adapter 校验来源和规格；缺 Lot 进入补录，不推断 PASS/FAIL",
    ),
    CleanerFormatMethod(
        method_code="LION_V1_DYNAMIC_EXCEL",
        display_name="立昂微 V1 动态参数 Excel",
        extensions=(".xls", ".xlsx"),
        detector_entrypoint="lion.lion_reader.LionExcelReader.can_read",
        parser_entrypoint="lion.lion_reader.LionExcelReader",
        fail_closed_notes=(
            "按工作簿内容识别；允许参数增减，同名参数单位、上下限或条件冲突时拒绝"
        ),
    ),
    CleanerFormatMethod(
        method_code="LION_V2_PROFILED_OLE_XLS",
        display_name="立昂微 V2 已批准 OLE XLS",
        extensions=(".xls",),
        detector_entrypoint="lion.lion_v2_reader.LionV2Reader.can_read",
        parser_entrypoint="lion.lion_v2_reader.LionV2Reader",
        fail_closed_notes="只接受已批准的 V2 布局、身份、规格和 pass_bin=1",
    ),
    CleanerFormatMethod(
        method_code="DIANJI_QA_BIFF_XLS",
        display_name="电基 QA Test System 二进制 XLS",
        extensions=(".xls",),
        detector_entrypoint="factories.dianji.qa_xls_parser.is_qa_xls_file",
        parser_entrypoint="factories.dianji.qa_xls_parser.parse_qa_xls_file",
        fail_closed_notes="仅已验证测试程序及固定布局；全记录、HARD_BIN、PASSFG与源汇总逐项核对",
    ),
    CleanerFormatMethod(
        method_code="DIANJI_POWERTECH_TEXT_XLS",
        display_name="电基 PowerTECH 文本伪 XLS",
        extensions=(".xls",),
        detector_entrypoint=(
            "factories.dianji.powertech_parser.is_powertech_text_file"
        ),
        parser_entrypoint="factories.dianji.powertech_parser.parse_powertech_file",
        fail_closed_notes="GB18030/Tab 文本；扩展名、内容签名和身份必须同时匹配",
    ),
    CleanerFormatMethod(
        method_code="DIANJI_POWERTECH_NATIVE_XLSX",
        display_name="电基 PowerTECH 原生 XLSX",
        extensions=(".xlsx",),
        detector_entrypoint=(
            "factories.dianji.powertech_xlsx_parser.is_powertech_xlsx_file"
        ),
        parser_entrypoint=(
            "factories.dianji.powertech_xlsx_parser.parse_powertech_xlsx_file"
        ),
        fail_closed_notes="只接受已验证产品、测试标签、布局和文件名组合",
    ),
    CleanerFormatMethod(
        method_code="DIANJI_STS8203_CSV",
        display_name="电基 STS8203 CSV",
        extensions=(".csv",),
        detector_entrypoint="factories.dianji.sts8203_parser.is_sts8203_csv_file",
        parser_entrypoint="factories.dianji.sts8203_parser.parse_sts8203_file",
        fail_closed_notes="校验 STS8203 签名、列数、单位、Lot 和产品映射",
    ),
    CleanerFormatMethod(
        method_code="DIANJI_TF_CSV",
        display_name="电基 TF CSV",
        extensions=(".csv",),
        detector_entrypoint="factories.dianji.tf_csv_parser.is_dianji_tf_csv_file",
        parser_entrypoint="factories.dianji.tf_csv_parser.parse_dianji_tf_file",
        fail_closed_notes="校验 TF 内容签名、元数据、参数和单位合同",
    ),
)


CLEANER_CAPABILITIES: tuple[CleanerCapability, ...] = (
    CleanerCapability("JIJIA_FT_FORMAL_CLEAN", "集佳 FT-ALL 正式清洗", "FT", "JIJIA",
        "JIJIA_FT_PYZ", "JIJIA_FT_EXISTING", "JIJIA_REGISTERED_DIRECTORY_V1",
        "FT_XLSX_SCATTER_V1", ("FORMAL_IMPORT",),
        ("JIJIA_STS8203_CSV", "JIJIA_DTA_CSV"), format_code="JIJIA_FT_REGISTERED_EXISTING"),
    CleanerCapability("JIEMIN_FT_FORMAL_CLEAN", "上海捷敏 DC / DVDS / RG 正式清洗", "FT", "JIEMIN",
        "JIEMIN_FT_PYZ", "JIEMIN_FT_EXISTING", "JIEMIN_REGISTERED_DIRECTORY_V1",
        "FT_XLSX_SCATTER_V1", ("FORMAL_IMPORT",),
        ("JIEMIN_PROFILED_XLS", "JIEMIN_RG_LCR"), format_code="JIEMIN_FT_REGISTERED_EXISTING"),
    CleanerCapability(
        "HUAHONG_CP_STANDARD_CLEAN",
        "华虹 CP 标准清洗",
        "CP",
        "HUAHONG",
        "HUAHONG_CP_PYZ",
        "HUAHONG_CP_EXISTING",
        "CP_ARCHIVE_OR_TXT_V1",
        "CP_CSV_TRIPLET_V1",
        ("FORMAL_IMPORT",),
        ("HUAHONG_DCP_TEXT", "HUAHONG_TD_EXCEL"),
        format_code="HUAHONG_DCP_EXISTING",
    ),
    CleanerCapability(
        "JETECH_CP_STANDARD_CLEAN",
        "佳泰 CP 标准清洗",
        "CP",
        "JETECH",
        "JETECH_CP_PYZ",
        "JETECH_CP_EXISTING",
        "CP_EXCEL_OR_ZIP_V1",
        "CP_STANDARD_CSV_TRIPLET_V1",
        ("FORMAL_IMPORT",),
        ("JETECH_CP_EXCEL",),
        format_code="JETECH_CP_EXISTING",
    ),
    CleanerCapability(
        "RIYUEXIN_FT_FORMAL_CLEAN",
        "日月新 FT 正式清洗",
        "FT",
        "RIYUEXIN",
        "RIYUEXIN_FT_PYZ",
        "RIYUEXIN_FT_EXISTING",
        "FT_DIRECTORY_XLSX_V1",
        "FT_XLSX_SCATTER_V1",
        ("FORMAL_IMPORT",),
        ("RIYUEXIN_DC_EXCEL",),
        format_code="RIYUEXIN_DC_EXISTING",
    ),
    CleanerCapability(
        "RIYUEGUANG_FT_FORMAL_CLEAN",
        "日月光 FT 正式清洗",
        "FT",
        "RIYUEGUANG",
        "RIYUEGUANG_FT_PYZ",
        "RIYUEGUANG_FT_EXISTING",
        "FT_DIRECTORY_XLSX_V1",
        "FT_XLSX_SCATTER_V1",
        ("FORMAL_IMPORT",),
        ("RIYUEGUANG_DC_EXCEL",),
        format_code="RIYUEGUANG_DC_EXISTING",
    ),
    CleanerCapability(
        capability_code="LION_CP_STANDARD_CLEAN",
        display_name="立昂微 CP 标准清洗",
        test_stage="CP",
        factory_code="LION",
        adapter_code="LION_CP_PYZ",
        cleaner_code="LION_CP_EXISTING",
        input_contract_version="CP_EXCEL_OR_ZIP_V1",
        output_contract_version="CP_STANDARD_CSV_TRIPLET_V1",
        use_scopes=("FORMAL_IMPORT", "PERSONAL_ANALYSIS"),
        format_method_codes=(
            "LION_V1_DYNAMIC_EXCEL",
            "LION_V2_PROFILED_OLE_XLS",
        ),
        format_code="LION_CP_EXISTING",
    ),
    CleanerCapability(
        capability_code="DIANJI_FT_FORMAL_CLEAN",
        display_name="电基 FT 正式清洗",
        test_stage="FT",
        factory_code="DIANJI",
        adapter_code="DIANJI_FT_PYZ",
        cleaner_code="DIANJI_FT_POWERTECH_EXISTING",
        input_contract_version="DIANJI_POWERTECH_DIRECTORY_V1",
        output_contract_version="DIANJI_FT_SCATTER_V1",
        use_scopes=("FORMAL_IMPORT",),
        format_method_codes=(
            "DIANJI_POWERTECH_TEXT_XLS",
            "DIANJI_POWERTECH_NATIVE_XLSX",
            "DIANJI_QA_BIFF_XLS",
            "DIANJI_STS8203_CSV",
            "DIANJI_TF_CSV",
        ),
        format_code="DIANJI_POWERTECH_DYNAMIC_EXISTING",
    ),
    CleanerCapability(
        capability_code="DIANJI_FT_PERSONAL_PAT",
        display_name="电基 FT 个人目录 PAT",
        test_stage="FT",
        factory_code="DIANJI",
        adapter_code="DIANJI_FT_QUICK_PAT_PYZ",
        cleaner_code="DIANJI_FT_QUICK_PAT_EXISTING",
        input_contract_version="DIANJI_REGISTERED_RAW_DIRECTORY_V1",
        output_contract_version="FT_PAT_RESULT_V1",
        use_scopes=("PERSONAL_ANALYSIS",),
        format_method_codes=(
            "DIANJI_POWERTECH_TEXT_XLS",
            "DIANJI_POWERTECH_NATIVE_XLSX",
            "DIANJI_STS8203_CSV",
            "DIANJI_TF_CSV",
        ),
    ),
)


_METHODS_BY_CODE = {item.method_code: item for item in FORMAT_METHODS}
_CAPABILITIES_BY_ADAPTER = {item.adapter_code: item for item in CLEANER_CAPABILITIES}


def cleaner_capability(adapter_code: str) -> CleanerCapability | None:
    return _CAPABILITIES_BY_ADAPTER.get(adapter_code.strip().upper())


def capability_format_methods(
    capability: CleanerCapability,
) -> tuple[CleanerFormatMethod, ...]:
    return tuple(_METHODS_BY_CODE[code] for code in capability.format_method_codes)


def capability_allowed_suffixes(adapter_code: str) -> frozenset[str] | None:
    capability = cleaner_capability(adapter_code)
    if capability is None:
        return None
    return frozenset(
        extension
        for method in capability_format_methods(capability)
        for extension in method.extensions
    )


def capability_catalog() -> list[dict[str, object]]:
    catalog: list[dict[str, object]] = []
    for capability in CLEANER_CAPABILITIES:
        payload = asdict(capability)
        payload["format_methods"] = [
            asdict(method) for method in capability_format_methods(capability)
        ]
        catalog.append(payload)
    return catalog


def validate_capability_contract(
    *,
    adapter_code: str,
    test_stage: str,
    factory_code: str,
    cleaner_code: str,
    input_contract_version: str,
    output_contract_version: str,
    execution_config_json: str | None = None,
) -> CleanerCapability | None:
    """Fail closed for known modular capabilities; ignore legacy adapters."""

    capability = cleaner_capability(adapter_code)
    if capability is None:
        return None
    actual = (
        test_stage.strip().upper(),
        factory_code.strip().upper(),
        cleaner_code.strip().upper(),
        input_contract_version.strip().upper(),
        output_contract_version.strip().upper(),
    )
    expected = (
        capability.test_stage,
        capability.factory_code,
        capability.cleaner_code,
        capability.input_contract_version,
        capability.output_contract_version,
    )
    if actual != expected:
        raise ValueError(
            "Cleaner Release does not match its modular capability contract: "
            f"{capability.capability_code}"
        )
    if execution_config_json:
        try:
            config = json.loads(execution_config_json)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Cleaner Release execution config is invalid JSON"
            ) from exc
        declared_capability = config.get("capability_code")
        declared_methods = config.get("format_method_codes")
        has_declaration = (
            declared_capability is not None or declared_methods is not None
        )
        accepted_methods = {capability.format_method_codes}
        if capability.adapter_code == "HUAHONG_CP_PYZ":
            accepted_methods.add(("HUAHONG_DCP_TEXT",))
        if capability.adapter_code == "JIEMIN_FT_PYZ":
            accepted_methods.add(("JIEMIN_PROFILED_XLS",))
        if capability.adapter_code == "DIANJI_FT_PYZ":
            # Existing immutable releases remain valid for their original formats.
            accepted_methods.add(("DIANJI_POWERTECH_TEXT_XLS", "DIANJI_POWERTECH_NATIVE_XLSX"))
            accepted_methods.add(("DIANJI_POWERTECH_TEXT_XLS", "DIANJI_POWERTECH_NATIVE_XLSX", "DIANJI_QA_BIFF_XLS"))
        mismatched_declaration = (
            declared_capability != capability.capability_code
            or not any(tuple(declared_methods or ()) == methods for methods in accepted_methods)
        )
        if has_declaration and mismatched_declaration:
            raise ValueError(
                "Cleaner Release format methods do not match its modular "
                f"capability contract: {capability.capability_code}"
            )
    return capability


FORMAL_CLEANER_CONTRACTS = {
    (item.test_stage, item.factory_code): {
        "format_code": item.format_code,
        "cleaner_code": item.cleaner_code,
        "adapter_code": item.adapter_code,
        "input_contract_version": item.input_contract_version,
        "output_contract_version": item.output_contract_version,
    }
    for item in CLEANER_CAPABILITIES
    if "FORMAL_IMPORT" in item.use_scopes and item.format_code is not None
}
