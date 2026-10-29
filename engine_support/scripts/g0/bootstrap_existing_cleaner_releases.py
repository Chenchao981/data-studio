from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class ExistingRelease:
    stage: str
    factory: str
    format_code: str
    cleaner_code: str
    package: Path
    adapter_code: str
    entrypoint: str
    input_contract: str
    output_contract: str
    cleaner_version: str | None = None
    capability_code: str | None = None
    format_method_codes: tuple[str, ...] = ()
    timeout_seconds: int = 3600
    max_output_bytes: int = 10 * 1024 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_package(package: Path, checksum: str, snapshot_root: Path) -> Path:
    """Copy a Cleaner package once into a content-addressed immutable location."""
    if _sha256(package) != checksum:
        raise RuntimeError(f"Cleaner package changed before snapshot: {package}")

    target_directory = snapshot_root.resolve() / checksum
    target_directory.mkdir(parents=True, exist_ok=True)
    target = target_directory / package.name
    if target.exists():
        if not target.is_file() or _sha256(target) != checksum:
            raise RuntimeError(f"Cleaner release snapshot checksum mismatch: {target}")
        return target.resolve()

    temporary = target_directory / f".{package.name}.{uuid4().hex}.tmp"
    try:
        with package.open("rb") as source, temporary.open("xb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if _sha256(temporary) != checksum:
            raise RuntimeError(f"Cleaner package changed while snapshotting: {package}")
        try:
            os.link(temporary, target)
        except FileExistsError:
            if not target.is_file() or _sha256(target) != checksum:
                raise RuntimeError(
                    f"Cleaner release snapshot checksum mismatch: {target}"
                )
    finally:
        temporary.unlink(missing_ok=True)

    if _sha256(target) != checksum:
        raise RuntimeError(f"Cleaner release snapshot checksum mismatch: {target}")
    return target.resolve()


def _definitions() -> tuple[ExistingRelease, ...]:
    cp_package = Path(
        os.getenv(
            "TMS_CP_CLEANER_PACKAGE",
            r"F:\cp_data_ansys\packaging\release\app.pyz",
        )
    ).resolve()
    ft_package = Path(
        os.getenv(
            "TMS_FT_CLEANER_PACKAGE",
            r"F:\data_IGBT_multiple\packaging\release\ft_data_cleaner.pyz",
        )
    ).resolve()
    dianji_methods = ("DIANJI_POWERTECH_TEXT_XLS", "DIANJI_POWERTECH_NATIVE_XLSX")
    if ft_package.is_file() and zipfile.is_zipfile(ft_package):
        with zipfile.ZipFile(ft_package) as archive:
            if "factories/dianji/qa_xls_parser.py" in archive.namelist():
                dianji_methods += ("DIANJI_QA_BIFF_XLS",)
            if "factories/dianji/dynamic_parser.py" in archive.namelist():
                dianji_methods += ("DIANJI_STS8203_CSV", "DIANJI_TF_CSV")
    return (
        ExistingRelease("FT", "JIJIA", "JIJIA_FT_REGISTERED_EXISTING", "JIJIA_FT_EXISTING",
            ft_package, "JIJIA_FT_PYZ", "factories.jijia.dc_cleaner.JijiaFTCleaner.process_all",
            "JIJIA_REGISTERED_DIRECTORY_V1", "FT_XLSX_SCATTER_V1", "v2.26.1",
            capability_code="JIJIA_FT_FORMAL_CLEAN", format_method_codes=("JIJIA_STS8203_CSV", "JIJIA_DTA_CSV")),
        ExistingRelease("FT", "JIEMIN", "JIEMIN_FT_REGISTERED_EXISTING", "JIEMIN_FT_EXISTING",
            ft_package, "JIEMIN_FT_PYZ", "factories.jiemin.dc_cleaner.JieminFTCleaner.process_all",
            "JIEMIN_REGISTERED_DIRECTORY_V1", "FT_XLSX_SCATTER_V1", "v2.26.15",
            capability_code="JIEMIN_FT_FORMAL_CLEAN", format_method_codes=("JIEMIN_PROFILED_XLS", "JIEMIN_RG_LCR")),
        ExistingRelease(
            "CP",
            "HUAHONG",
            "HUAHONG_DCP_EXISTING",
            "HUAHONG_CP_EXISTING",
            cp_package,
            "HUAHONG_CP_PYZ",
            "prepare_dcp_input -> clean_dcp_data.process_directory",
            "CP_ARCHIVE_OR_TXT_V1",
            "CP_CSV_TRIPLET_V1",
        ),
        ExistingRelease(
            "CP",
            "JETECH",
            "JETECH_CP_EXISTING",
            "JETECH_CP_EXISTING",
            cp_package,
            "JETECH_CP_PYZ",
            "jt_data_processor.jt_main_processor.process_jt_files",
            "CP_EXCEL_OR_ZIP_V1",
            "CP_STANDARD_CSV_TRIPLET_V1",
        ),
        ExistingRelease(
            "CP",
            "LION",
            "LION_CP_EXISTING",
            "LION_CP_EXISTING",
            cp_package,
            "LION_CP_PYZ",
            "lion_batch_processor.generate_lion_run_csvs",
            "CP_EXCEL_OR_ZIP_V1",
            "CP_STANDARD_CSV_TRIPLET_V1",
            capability_code="LION_CP_STANDARD_CLEAN",
            format_method_codes=(
                "LION_V1_DYNAMIC_EXCEL",
                "LION_V2_PROFILED_OLE_XLS",
            ),
        ),
        ExistingRelease(
            "CP",
            "GUOYU",
            "GUOYU_FRD_CP_EXISTING",
            "GUOYU_FRD_CP_EXISTING",
            cp_package,
            "GUOYU_CP_PYZ",
            "guoyu_batch_processor.process_guoyu_directory",
            "CP_EXCEL_OR_ZIP_V1",
            "CP_STANDARD_CSV_TRIPLET_V1",
        ),
        ExistingRelease(
            "FT",
            "RIYUEXIN",
            "RIYUEXIN_DC_EXISTING",
            "RIYUEXIN_FT_EXISTING",
            ft_package,
            "RIYUEXIN_FT_PYZ",
            "factories.tms_adapters.riyuexin_dc.RiyuexinTmsDCCleaner.process_all_dc_files",
            "FT_DIRECTORY_XLSX_V1",
            "FT_XLSX_SCATTER_V1",
        ),
        ExistingRelease(
            "FT",
            "RIYUEGUANG",
            "RIYUEGUANG_DC_EXISTING",
            "RIYUEGUANG_FT_EXISTING",
            ft_package,
            "RIYUEGUANG_FT_PYZ",
            "factories.tms_adapters.riyueguang_dc.RiyueguangTmsDCCleaner.process_all_dc_files",
            "FT_DIRECTORY_XLSX_V1",
            "FT_XLSX_SCATTER_V1",
        ),
        ExistingRelease(
            "FT",
            "DIANJI",
            "DIANJI_POWERTECH_DYNAMIC_EXISTING",
            "DIANJI_FT_POWERTECH_EXISTING",
            ft_package,
            "DIANJI_FT_PYZ",
            "factories.dianji.dc_cleaner.DianjiDCCleaner.process_all via TMS manifest adapter",
            "DIANJI_POWERTECH_DIRECTORY_V1",
            "DIANJI_FT_SCATTER_V1",
            "v2.26.1",
            capability_code="DIANJI_FT_FORMAL_CLEAN",
            format_method_codes=dianji_methods,
        ),
        ExistingRelease(
            "FT",
            "JIEQUN",
            "JIEQUN_FT_QUICK_PAT_EXISTING",
            "JIEQUN_FT_QUICK_PAT_EXISTING",
            ft_package,
            "JIEQUN_FT_QUICK_PAT_PYZ",
            "factories.jiequn.pat_cleaner.generate_raw_pat",
            "JIEQUN_UNIFIED_CSV_DIRECTORY_V1",
            "FT_PAT_RESULT_V1",
            timeout_seconds=7200,
            max_output_bytes=64 * 1024 * 1024,
        ),
        ExistingRelease(
            "FT",
            "RIYUEXIN",
            "RIYUEXIN_FT_QUICK_PAT_EXISTING",
            "RIYUEXIN_FT_QUICK_PAT_EXISTING",
            ft_package,
            "RIYUEXIN_FT_QUICK_PAT_PYZ",
            "factories.riyuexin.pat_cleaner.generate_raw_pat",
            "RIYUEXIN_RAW_XLSX_DIRECTORY_V1",
            "FT_PAT_RESULT_V1",
            "v2.20.0-pat",
            timeout_seconds=7200,
            max_output_bytes=64 * 1024 * 1024,
        ),
        ExistingRelease(
            "FT",
            "DIANJI",
            "DIANJI_FT_QUICK_PAT_EXISTING",
            "DIANJI_FT_QUICK_PAT_EXISTING",
            ft_package,
            "DIANJI_FT_QUICK_PAT_PYZ",
            "factories.dianji.pat_cleaner.generate_raw_pat",
            "DIANJI_REGISTERED_RAW_DIRECTORY_V1",
            "FT_PAT_RESULT_V1",
            "v2.20.0-pat",
            capability_code="DIANJI_FT_PERSONAL_PAT",
            format_method_codes=(
                "DIANJI_POWERTECH_TEXT_XLS",
                "DIANJI_POWERTECH_NATIVE_XLSX",
                "DIANJI_STS8203_CSV",
                "DIANJI_TF_CSV",
            ),
            timeout_seconds=7200,
            max_output_bytes=64 * 1024 * 1024,
        ),
        ExistingRelease(
            "FT",
            "RIYUEGUANG",
            "RIYUEGUANG_FT_QUICK_PAT_EXISTING",
            "RIYUEGUANG_FT_QUICK_PAT_EXISTING",
            ft_package,
            "RIYUEGUANG_FT_QUICK_PAT_PYZ",
            "factories.tms_adapters.riyueguang_pat.generate_raw_pat",
            "RIYUEGUANG_RAW_XLSX_DIRECTORY_V1",
            "FT_PAT_RESULT_V1",
            "v2.20.0-pat",
            timeout_seconds=7200,
            max_output_bytes=64 * 1024 * 1024,
        ),
        ExistingRelease(
            "FT",
            "JIJIA",
            "JIJIA_FT_QUICK_PAT_EXISTING",
            "JIJIA_FT_QUICK_PAT_EXISTING",
            ft_package,
            "JIJIA_FT_QUICK_PAT_PYZ",
            "factories.jijia.pat_cleaner.generate_raw_pat",
            "JIJIA_STS8203_CSV_DIRECTORY_V1",
            "FT_PAT_RESULT_V1",
            "v2.20.0-pat",
            timeout_seconds=7200,
            max_output_bytes=64 * 1024 * 1024,
        ),
        ExistingRelease(
            "FT", "JIEMIN", "JIEMIN_FT_QUICK_PAT_EXISTING",
            "JIEMIN_FT_QUICK_PAT_EXISTING", ft_package,
            "JIEMIN_FT_QUICK_PAT_PYZ", "factories.jiemin.pat_cleaner.generate_raw_pat",
            "JIEMIN_RAW_XLS_DIRECTORY_V1", "FT_PAT_RESULT_V1",
            timeout_seconds=7200, max_output_bytes=64 * 1024 * 1024,
        ),
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register immutable snapshots for explicitly selected Cleaner factories"
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--factory",
        action="append",
        choices=(
            "HUAHONG",
            "JETECH",
            "LION",
            "GUOYU",
            "RIYUEXIN",
            "RIYUEGUANG",
            "DIANJI",
            "JIEQUN",
            "JIJIA",
            "JIEMIN",
        ),
        help="Register only this factory; repeat to select more than one",
    )
    selection.add_argument(
        "--all",
        action="store_true",
        help="Explicitly register every configured Cleaner definition",
    )
    parser.add_argument("--personal-tools-only", action="store_true", help="Limit registration to FT quick tools; leave formal ingestion releases unchanged")
    parser.add_argument("--formal-only", action="store_true", help="Register formal ingestion only; leave personal tool releases unchanged")
    parser.add_argument("--version", help="Explicit new immutable Cleaner version for the selected definitions")
    parser.add_argument("--max-output-mb", type=int, help="Output budget for a new selected immutable version")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    database_url = os.environ.get("TMS_DATABASE_URL")
    if not database_url:
        raise RuntimeError("TMS_DATABASE_URL is required")
    runtime = Path(
        os.getenv("TMS_CLEANER_PYTHON", r"D:\ProgramData\anaconda3\python.exe")
    ).resolve()
    snapshot_root = Path(
        os.getenv(
            "TMS_CLEANER_RELEASE_SNAPSHOT_ROOT",
            str(ROOT / "artifacts" / "cleaner_releases"),
        )
    ).resolve()
    if not runtime.is_file():
        raise FileNotFoundError(f"Cleaner Python runtime is unavailable: {runtime}")

    releases = _definitions()
    if not args.all:
        selected = set(args.factory or ())
        releases = tuple(item for item in releases if item.factory in selected)
    if args.personal_tools_only:
        releases = tuple(item for item in releases if item.adapter_code.endswith("_FT_QUICK_PAT_PYZ"))
    if args.formal_only:
        releases = tuple(item for item in releases if not item.adapter_code.endswith("_FT_QUICK_PAT_PYZ"))
    if args.version:
        releases = tuple(replace(item, cleaner_version=args.version) for item in releases)
    if args.max_output_mb is not None:
        if not args.version or not 1 <= args.max_output_mb <= 102400:
            raise ValueError("--max-output-mb requires a new --version and a value from 1 to 102400")
        releases = tuple(replace(item, max_output_bytes=args.max_output_mb * 1024**2) for item in releases)
    if not releases:
        raise RuntimeError("no Cleaner definitions were selected")
    for release in releases:
        if not release.package.is_file():
            raise FileNotFoundError(
                f"Cleaner package is unavailable: {release.package}"
            )

    engine = create_engine(database_url)
    registered: list[dict[str, object]] = []
    with engine.begin() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        if revision not in {"sql2014_0035", "sql2014_0036", "sql2014_0037", "sql2014_0038", "sql2014_0039", "sql2014_0040", "sql2014_0041", "sql2014_0042", "sql2014_0043", "sql2014_0044", "sql2014_0045", "sql2014_0046", "sql2014_0047", "sql2014_0048", "sql2014_0049", "sql2014_0050", "sql2014_0053", "sql2014_0054", "sql2014_0055", "sql2014_0056", "sql2014_0057"}:
            raise RuntimeError(f"Unsupported Cleaner registry schema: {revision}")
        approved_by = connection.execute(
            text(
                "SELECT TOP (1) u.user_id FROM iam.app_user u "
                "JOIN iam.user_role ur ON ur.user_id=u.user_id "
                "JOIN iam.role r ON r.role_id=ur.role_id "
                "WHERE r.role_code='SYSTEM_ADMIN' AND u.status='ACTIVE' "
                "ORDER BY u.user_id"
            )
        ).scalar_one_or_none()

        for definition in releases:
            checksum = _sha256(definition.package)
            artifact = _snapshot_package(
                definition.package,
                checksum,
                snapshot_root,
            )
            version = definition.cleaner_version or f"sha256-{checksum[:12]}"
            profile_id = connection.execute(
                text(
                    "SELECT format_profile_id FROM ingestion.format_profile "
                    "WHERE format_code=:format_code AND profile_version='route-a-v1'"
                ),
                {"format_code": definition.format_code},
            ).scalar_one_or_none()
            if profile_id is None:
                profile_id = connection.execute(
                    text(
                        "INSERT ingestion.format_profile("
                        "supplier_id,test_stage,factory_code,format_code,profile_version,"
                        "signature_json,file_role_contract_json,status,approved_by,approved_at_utc) "
                        "OUTPUT INSERTED.format_profile_id VALUES("
                        "NULL,:stage,:factory,:format_code,'route-a-v1',:signature,:roles,"
                        "'RELEASED',:approved_by,SYSUTCDATETIME())"
                    ),
                    {
                        "stage": definition.stage,
                        "factory": definition.factory,
                        "format_code": definition.format_code,
                        "signature": json.dumps(
                            {"selection": "explicit factory selection"},
                            ensure_ascii=False,
                        ),
                        "roles": json.dumps(
                            {
                                "input_contract": definition.input_contract,
                                "output_contract": definition.output_contract,
                            },
                            ensure_ascii=False,
                        ),
                        "approved_by": approved_by,
                    },
                ).scalar_one()
            else:
                connection.execute(
                    text(
                        "UPDATE ingestion.format_profile SET factory_code=:factory,"
                        "test_stage=:stage,status='RELEASED' WHERE format_profile_id=:profile_id"
                    ),
                    {
                        "factory": definition.factory,
                        "stage": definition.stage,
                        "profile_id": profile_id,
                    },
                )

            release_row = (
                connection.execute(
                    text(
                        "SELECT cleaner_release_id,code_checksum,status,artifact_uri,"
                        "runtime_uri,entrypoint,adapter_code,input_contract_version,"
                        "output_contract_version,execution_config_json,timeout_seconds,"
                        "max_output_bytes FROM ingestion.cleaner_release "
                        "WHERE cleaner_code=:cleaner_code AND cleaner_version=:version "
                        "AND format_profile_id=:profile_id"
                    ),
                    {
                        "cleaner_code": definition.cleaner_code,
                        "version": version,
                        "profile_id": profile_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            release_id = (
                int(release_row["cleaner_release_id"])
                if release_row is not None
                else None
            )
            if (
                release_row is not None
                and str(release_row["code_checksum"] or "").lower() != checksum
            ):
                raise RuntimeError(
                    f"Cleaner version checksum collision: {definition.cleaner_code}/{version}"
                )
            values = {
                "profile_id": profile_id,
                "cleaner_code": definition.cleaner_code,
                "version": version,
                "checksum": checksum,
                "artifact_uri": str(artifact),
                "runtime_uri": str(runtime),
                "entrypoint": definition.entrypoint,
                "adapter_code": definition.adapter_code,
                "input_contract": definition.input_contract,
                "output_contract": definition.output_contract,
                "config": json.dumps(
                    {
                        "factory_code": definition.factory,
                        **(
                            {
                                "capability_code": definition.capability_code,
                                "format_method_codes": list(
                                    definition.format_method_codes
                                ),
                            }
                            if definition.capability_code
                            else {}
                        ),
                        **(
                            {"outlier_method": "iqr", "convert_units": True}
                            if definition.stage == "CP"
                            else {}
                        ),
                    },
                    ensure_ascii=False,
                ),
                "timeout_seconds": definition.timeout_seconds,
                "max_output_bytes": definition.max_output_bytes,
                "approved_by": approved_by,
            }
            if release_id is None:
                release_id = connection.execute(
                    text(
                        "INSERT ingestion.cleaner_release("
                        "format_profile_id,cleaner_code,cleaner_version,code_checksum,"
                        "artifact_uri,status,approved_by,approved_at_utc,runtime_uri,entrypoint,"
                        "adapter_code,input_contract_version,output_contract_version,"
                        "execution_config_json,timeout_seconds,max_output_bytes) "
                        "OUTPUT INSERTED.cleaner_release_id VALUES("
                        ":profile_id,:cleaner_code,:version,:checksum,:artifact_uri,'RELEASED',"
                        ":approved_by,SYSUTCDATETIME(),"
                        ":runtime_uri,:entrypoint,:adapter_code,"
                        ":input_contract,:output_contract,:config,:timeout_seconds,"
                        ":max_output_bytes)"
                    ),
                    values,
                ).scalar_one()
            else:
                expected_contract = {
                    "status": "RELEASED",
                    "artifact_uri": values["artifact_uri"],
                    "runtime_uri": values["runtime_uri"],
                    "entrypoint": values["entrypoint"],
                    "adapter_code": values["adapter_code"],
                    "input_contract_version": values["input_contract"],
                    "output_contract_version": values["output_contract"],
                    "timeout_seconds": values["timeout_seconds"],
                    "max_output_bytes": values["max_output_bytes"],
                }
                mismatches = [
                    field
                    for field, expected in expected_contract.items()
                    if (
                        int(release_row[field])
                        if field in {"timeout_seconds", "max_output_bytes"}
                        else str(release_row[field] or "")
                    )
                    != expected
                ]
                try:
                    stored_config = json.loads(
                        str(release_row["execution_config_json"] or "null")
                    )
                    expected_config = json.loads(str(values["config"]))
                except json.JSONDecodeError:
                    mismatches.append("execution_config_json")
                else:
                    if stored_config != expected_config:
                        mismatches.append("execution_config_json")
                if mismatches:
                    raise RuntimeError(
                        "Cleaner Release rows are immutable; register a new "
                        f"version instead (release_id={release_id}, fields="
                        + ",".join(sorted(set(mismatches)))
                        + ")"
                    )
            registered.append(
                {
                    "cleaner_release_id": int(release_id),
                    "stage": definition.stage,
                    "factory": definition.factory,
                    "version": version,
                    "status": "RELEASED",
                    "artifact_uri": str(artifact),
                    "output_contract": definition.output_contract,
                    "timeout_seconds": definition.timeout_seconds,
                    "max_output_bytes": definition.max_output_bytes,
                }
            )
    print(json.dumps({"registered": registered}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
