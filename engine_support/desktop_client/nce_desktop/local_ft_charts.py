"""Runs only inside an isolated engine process; no changes to factory algorithms."""

import json
import sys
from pathlib import Path

if __package__:
    from .parameter_visibility import visible_parameter_names
else:
    from parameter_visibility import visible_parameter_names


def main():
    package, factory, source, work, output = sys.argv[1:]
    sys.path.insert(0, package)
    source, work, output = Path(source), Path(work), Path(output)
    target = work / "chart-input"
    target.mkdir()
    if factory == "JIEMIN":
        from factories.jiemin.dc_cleaner import JieminFTCleaner

        cleaner = JieminFTCleaner(source, target, export_artifacts=True)
        ok = cleaner.process_all()
        manifest = cleaner.last_scatter_manifest
    elif factory == "DIANJI":
        from factories.dianji.dc_cleaner import DianjiDCCleaner

        cleaner = DianjiDCCleaner(source, target, export_artifacts=True)
        ok = cleaner.process_all()
        manifest = cleaner.last_scatter_manifest
    elif factory == "RIYUEXIN":
        from factories.riyuexin.dc_cleaner import DCDataCleaner

        dc = source / "DC" if (source / "DC").is_dir() else source
        if dc.name.upper() in {"DVDS", "RG"}:
            raise ValueError("请选择DC原始目录")
        cleaner = DCDataCleaner(
            input_dir=str(dc), output_dir=str(target), export_artifacts=True
        )
        ok = cleaner.process_all_dc_files()
        manifest = cleaner.last_scatter_manifest
    elif factory == "JIEQUN":
        from factories.jiequn.dc_auto import detect_dc_format, DC_FORMAT_UNIFIED

        detection = detect_dc_format(source)
        if detection.format_name == DC_FORMAT_UNIFIED:
            from factories.jiequn.clean_unified import run_with_result

            result = run_with_result(
                detection.source_dir, target, export_artifacts=True
            )
            ok = bool(result)
            manifest = result.scatter_manifest
        else:
            from factories.jiequn.dc_cleaner import JiequnDCCleaner

            cleaner = JiequnDCCleaner(
                detection.source_dir, target, export_artifacts=True
            )
            ok = cleaner.process_all()
            manifest = cleaner.last_scatter_manifest
    else:
        raise ValueError("本版未接入此工厂的图表入口")
    if not ok or not manifest:
        raise ValueError("未生成完整图表输入，停止绘图")
    from frontend.ft_scatter import load_scatter_bundle
    from frontend.ft_static_charts import (
        prepare_ft_chart_layout,
        render_ft_scatter_png,
        render_ft_boxplot_png,
        safe_png_name,
    )

    meta, data, spec = load_scatter_bundle(manifest)
    parameters = visible_parameter_names(meta.get("parameters") or [])
    if not parameters:
        raise ValueError("没有可绘图的参数（CONT类项目不参与分析）")
    layout = prepare_ft_chart_layout(data)
    stats = {}
    for i, param in enumerate(parameters, 1):
        for kind, fn in [
            ("散点图", render_ft_scatter_png),
            ("箱体图", render_ft_boxplot_png),
        ]:
            for focus, label in [(True, "聚焦"), (False, "全范围")]:
                png, summary = fn(data, spec, param, layout, focus=focus)
                name = f"{i:03d}_" + safe_png_name(param, kind + "_" + label)
                (output / name).write_bytes(png)
                stats[name] = summary
        print(f'参数图片 {i}/{len(parameters)}', flush=True)
    (output / "chart_statistics.json").write_text(
        json.dumps(stats, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print("PYMS_RECORD_COUNT=" + str(meta.get("row_count", len(data))))


if __name__ == "__main__":
    main()
