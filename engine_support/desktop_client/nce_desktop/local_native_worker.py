"""Standalone native dispatch. Import engine modules only after pinning the PYZ path."""

import importlib
import logging
import json
from pathlib import Path
import sys
import shutil
from tempfile import TemporaryDirectory


def clean_cp(factory, sources, output):
    if factory == 'HUAHONG':
        return _clean_cp(factory,sources,output)
    # Retain the parent folder name when accepting a single raw file.
    with TemporaryDirectory(prefix="cp-input-", dir=output.parent.parent) as temporary:
        if (
            len(sources) == 1
            and sources[0].is_file()
            and sources[0].suffix.lower() not in {".zip", ".rar", ".7z"}
        ):
            folder = Path(temporary) / sources[0].parent.name
            folder.mkdir()
            shutil.copy2(sources[0], folder / sources[0].name)
            sources = [folder]
        return _clean_cp(factory, sources, output)


def _clean_cp(factory, sources, output):
    from cp_data_processor.processing.archive_input import prepare_archive_input
    from cp_data_processor.processing.output_naming import create_output_run_dir

    if factory == "HUAHONG":
        from local_cp_input import prepare_huahong_inputs
        from clean_dcp_data import process_directory

        with prepare_huahong_inputs(sources, output.parent.parent) as prepared:
            result = process_directory(
                str(prepared),
                str(output),
                outlier_method="iqr",
                convert_units=True,
            )
            if not result:
                raise ValueError("华虹DCP未生成有效结果")
        import csv
        cleaned = next(output.glob('*_cleaned_*.csv'))
        with cleaned.open(encoding='utf-8-sig',newline='') as stream:
            lot = next(csv.DictReader(stream))['Lot_ID']
        files = [p for p in output.iterdir() if p.is_file()]
        target = create_output_run_dir(output,lot)
        if not target.resolve().is_relative_to(output.resolve()):raise ValueError('输出目录无效')
        for file in files:file.rename(target/file.name)
        return
    with prepare_archive_input(
        sources,
        allowed_suffixes=(".xls", ".xlsx"),
        archive_suffixes=(".zip", ".rar") if factory == "LION" else (".zip",),
        preserve_member_paths=factory == "GUOYU",
        source_label=factory,
        progress=print,
    ) as prepared:
        if factory == "JETECH":
            from jt_data_processor.jt_main_processor import process_jt_files

            if not process_jt_files(
                input_paths=[str(p) for p in prepared.data_files],
                output_dir=str(output),
                pass_bin=1,
            ):
                raise ValueError("佳泰未生成有效结果")
        elif factory == "GUOYU":
            from guoyu_batch_processor import process_guoyu_directory

            process_guoyu_directory(str(prepared.directory), str(output))
        elif factory == "LION":
            from lion_batch_processor import (
                discover_batch_files,
                process_lion_batch_files,
                create_batch_lot,
                generate_lion_run_csvs,
            )

            groups = discover_batch_files(prepared.directory)
            if not groups:
                raise ValueError("未找到立昂微批次")
            lots = [
                create_batch_lot(process_lion_batch_files(files))
                for files in groups.values()
            ]
            target = create_output_run_dir(output, lots[0].lot_id)
            generate_lion_run_csvs(lots, str(target))
        else:
            raise ValueError("未知CP厂家")


def execute(package, code, sources, stage):
    # The original FT GUI attaches an INFO handler in CleanerWorker. Its headless
    # equivalent must expose those same messages to the per-task stdout log.
    if code.startswith('LOCAL_FT_'):
        logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                            format='%(asctime)s · %(levelname)s · %(message)s',
                            datefmt='%H:%M:%S')
    sys.path.insert(0, str(package))
    output = stage / "files"
    output.mkdir()
    record_count = None
    parameter_count = None
    source = sources[0]
    if code == "LOCAL_CP_HUAHONG_TD_V1":
        from cp_data_processor.processing.hh_td_processor import process_hh_td

        result = process_hh_td(sources, output, progress=print)
        record_count = sum(
            len(wafer.chip_data) for lot in result.lots.values() for wafer in lot.wafers
        )
    elif code in {"LOCAL_CP_HUAHONG_RAW_PAT_V1", "HUAHONG_CP_QUICK_PAT_EXISTING::PAT"}:
        from local_cp_pat import generate_huahong_pat
        info = generate_huahong_pat(sources, output)
        record_count, parameter_count = info['record_count'], info['parameter_count']
    elif code in {f'{factory}_CP_QUICK_PAT_EXISTING::PAT' for factory in ('JETECH','LION','GUOYU')}:
        from local_cp_ft_pat import generate_cp_ft_pat
        factory = code.split('_')[0]
        intermediate = stage/'cp-pat-intermediate'
        intermediate.mkdir()
        if factory == 'GUOYU':
            from local_guoyu_pat_input import prepare_guoyu_pat
            prepare_guoyu_pat(sources, intermediate)
        else:
            clean_cp(factory, sources, intermediate)
        info = generate_cp_ft_pat(factory, intermediate, output)
        record_count, parameter_count = info['record_count'], info['parameter_count']
    elif code.startswith("LOCAL_CP_"):
        if 'PAT' in code:
            raise ValueError('此CP PAT尚未接入统一FT统计适配，禁止回退旧算法')
        clean_cp(code.split("_")[2], sources, output)
    else:
        # Code structure is generated by the desktop registry, never evaluated as Python.
        parts = code.split("_")
        factory, mode = parts[2].lower(), "_".join(parts[3:-1])
        if mode in {"RAW_PAT", "CLEANED_PAT"}:
            module = importlib.import_module(f"factories.{factory}.pat_cleaner")
            fn = module.generate_raw_pat if mode == "RAW_PAT" else module.generate_pat
            result = fn(source_dir=str(source), output_dir=str(output))
        elif factory == "jiequn" and mode == "DC":
            from factories.jiequn.dc_auto import run_auto_dc

            result = run_auto_dc(input_dir=str(source), output_dir=str(output))
        else:
            names = {
                ("jiequn", "DVDS"): (
                    "dvds_cleaner",
                    "JiequnDVDSCleaner",
                    "process_all",
                ),
                ("jiequn", "RG"): ("rg_cleaner", "JiequnRGCleaner", "process_all"),
                ("riyuexin", "DC"): (
                    "dc_cleaner",
                    "DCDataCleaner",
                    "process_all_dc_files",
                ),
                ("riyuexin", "RG"): ("rg_cleaner", "RGCleaner", "run"),
                ("jiemin", "FT_ALL"): ("dc_cleaner", "JieminFTCleaner", "process_all"),
                ("jiemin", "DVDS"): ("dvds_cleaner", "JieminDVDSCleaner", "process_all"),
                ("jiemin", "RG"): ("rg_cleaner", "JieminRGCleaner", "process_all"),
                ("dianji", "FT_ALL"): ("dc_cleaner", "DianjiDCCleaner", "process_all"),
                ("jijia", "FT_ALL"): ("dc_cleaner", "JijiaFTCleaner", "process_all"),
            }
            if factory == "riyuexin" and mode == "DVDS":
                from factories.riyuexin.dvds_cleaner import DVDSCleaner

                # Native documented configuration fields; constructor side-effects stay in the task.
                cleaner = DVDSCleaner(base_dir=str(stage))
                cleaner.dvds_dir, cleaner.output_dir = str(source), str(output)
                result = cleaner.process_all()
            else:
                module, name, method = names[(factory, mode)]
                cls = getattr(
                    importlib.import_module(f"factories.{factory}.{module}"), name
                )
                cleaner = cls(input_dir=str(source), output_dir=str(output))
                result = getattr(cleaner, method)()
        if not result:
            raise RuntimeError("原工具未完成所选操作，请检查格式和日志")
    (stage / "native-summary.json").write_text(
        json.dumps(
            {
                "tool_code": code,
                "record_count": record_count,
                "parameter_count": parameter_count,
                "basis": "原工具输出；未报告的计数保留未知",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    execute(
        Path(sys.argv[1]),
        sys.argv[2],
        [Path(p) for p in json.loads(sys.argv[3])],
        Path(sys.argv[4]),
    )
