"""Data Studio's CP viewer adaptation, applied only to a disposable PYZ copy.

The pinned reader, specifications and optional chart implementations stay intact.
Unselected chart bodies must never execute: Streamlit tabs alone are eager.
"""
from __future__ import annotations

import ast
from io import BytesIO
from pathlib import Path
import hashlib

COMBINED = "📊 箱线散点图"
OPTIONAL = (
    "🎯 BIN总览", "📋 Pareto", "📈 良率趋势", "📊 箱体图", "🔵 散点图",
    "🗺️ Wafer Mapping", "🎯 区域分析", "🔍 失效叠加", "📊 Wafer Summary",
    "⚠ Cpk/超限", "💾 数据表",
)


def adapt_dashboard(script: Path) -> None:
    """Fail closed if the pinned dashboard's layout or redraw contract changes."""
    tree = ast.parse(script.read_text(encoding="utf8"))
    selectors = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name == "available_parameters"]
    if len(selectors) != 1:
        raise ValueError("CP参数目录入口已改变，不能应用CONT过滤")
    selectors[0].decorator_list.append(ast.Name(id="_studio_analysis_names", ctx=ast.Load()))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    tabs = next(n for n in main.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "tabs" for t in n.targets))
    if not (isinstance(tabs.value, ast.Call) and ast.unparse(tabs.value.func) == "st.tabs"
            and ast.literal_eval(tabs.value.args[0]) == list(OPTIONAL)):
        raise ValueError("此CP图表版本需要更新按需绘图适配")
    blocks = [n for n in main.body if isinstance(n, ast.With)
              and ast.unparse(n.items[0].context_expr).startswith("tabs[")]
    if [ast.unparse(n.items[0].context_expr) for n in blocks] != [f"tabs[{i}]" for i in range(len(OPTIONAL))]:
        raise ValueError("CP图表分组已改变，不能应用按需绘图适配")
    draft = next(n for n in main.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "draft_filters" for t in n.targets))
    if not isinstance(draft.value, ast.Dict) or [ast.literal_eval(k) for k in draft.value.keys] != ["token", "lots", "wafers", "parameters"]:
        raise ValueError("CP图表筛选契约已改变")
    apply = next(n for n in main.body if isinstance(n, ast.If) and ast.unparse(n.test) == "draw_requested")
    pending = next(n for n in main.body if isinstance(n, ast.If) and ast.unparse(n.test) == "applied_filters != draft_filters")
    if len(pending.body) != 2 or ast.unparse(pending.body[-1]) != "st.stop()":
        raise ValueError("CP图表应用状态已改变")

    # Default to one parameter. All parameters remain available explicitly.
    parameter_controls = [n for n in ast.walk(main) if isinstance(n, ast.Call)
                          and ast.unparse(n.func) == "filter_container.checkbox"
                          and n.args and isinstance(n.args[0], ast.Constant)
                          and n.args[0].value == "全选参数"]
    if len(parameter_controls) != 1:
        raise ValueError("CP参数选择器已改变")
    next(k for k in parameter_controls[0].keywords if k.arg == "value").value = ast.Constant(False)
    main.body[main.body.index(draft):main.body.index(draft)] = ast.parse(
        "_studio_chart_form = filter_container.form('studio_chart_selection', border=False)\n"
        "selected_extra_charts = _studio_chart_form.multiselect('其他图形', "
        f"{list(OPTIONAL)!r}, default=[], key='studio_extra_charts')").body
    draw = next(n for n in main.body if isinstance(n, ast.Assign)
                and ast.unparse(n.targets[0]) == "draw_requested")
    draw.value.func = ast.parse("_studio_chart_form.form_submit_button", mode="eval").body
    draft.value.keys.extend(map(ast.Constant, ["charts", "pass_bin", "max_points"]))
    draft.value.values.extend(map(lambda s: ast.parse(s, mode="eval").body,
                                  ["list(selected_extra_charts)", "pass_bin", "max_points"]))
    apply.test = ast.parse("draw_requested or st.session_state.get('_analysis_applied_filters') is None", mode="eval").body
    # Pending selections retain the last applied graphs; no optional body is run
    # until its selection is committed with the redraw button.
    pending.body.pop()
    params_apply = next(n for n in main.body if isinstance(n, ast.Assign)
                        and ast.unparse(n.value) == "list(applied_filters['parameters'])")
    params_apply.value = ast.parse("_studio_visible_names(applied_filters['parameters'])", mode="eval").body
    i = main.body.index(params_apply) + 1
    main.body[i:i] = ast.parse("pass_bin = applied_filters['pass_bin']\nmax_points = applied_filters['max_points']").body
    tabs.value = ast.parse("_studio_tabs(st, applied_filters['charts'])", mode="eval").body
    i = main.body.index(tabs) + 1
    main.body[i:i] = ast.parse(
        f"with tabs[{COMBINED!r}]:\n    _studio_combined(st, dataset, params, get_spec_info)").body
    for index, block in enumerate(blocks):
        title = OPTIONAL[index]
        block.items[0].context_expr = ast.parse(f"tabs[{title!r}]", mode="eval").body
        main.body[main.body.index(block)] = ast.If(
            test=ast.parse(f"{title!r} in tabs", mode="eval").body, body=[block], orelse=[])
    for n in ast.walk(main):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            n.value = n.value.replace("🎨 绘制图形", "🔄 重新绘制").replace("绘制图形", "重新绘制")
    # Keep __future__ imports first.
    position = max((i + 1 for i, node in enumerate(tree.body)
                    if isinstance(node, ast.ImportFrom) and node.module == "__future__"), default=0)
    tree.body[position:position] = ast.parse(
        "from nce_desktop.cp_chart_controls import selected_tabs as _studio_tabs, render_combined as _studio_combined\n"
        "from nce_desktop.parameter_visibility import analysis_parameter_result as _studio_analysis_names, visible_parameter_names as _studio_visible_names").body
    ast.fix_missing_locations(tree)
    source = ast.unparse(tree) + "\n"
    compile(source, str(script), "exec")
    script.write_text(source, encoding="utf8")


def selected_tabs(st, selected):
    labels = [COMBINED, *(title for title in OPTIONAL if title in selected)]
    return dict(zip(labels, st.tabs(labels)))


def combined_figure(cleaned, parameter, spec_info, groups, *, focus=True):
    """Original per-wafer 1.5-IQR boxes plus every finite source measurement.

    Reuse the pinned box statistics, Lot/Wafer grouping, colors and viewport.
    Deterministic jitter changes X only; Y and repeat measurements are preserved.
    """
    import numpy as np
    import pandas as pd
    from frontend.charts.lot_scatter import _make_lot_boxplot_figure, _lot_color

    fig = _make_lot_boxplot_figure(cleaned, parameter, spec_info, groups, focus=focus)
    ax = fig.axes[0]
    original_range = ax.get_ylim()
    values = pd.to_numeric(cleaned[parameter], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    for patch in ax.patches:
        patch.set_alpha(0.18)
    for lot_index, group in enumerate(groups):
        for wafer_index, (start, end) in enumerate(group.wafer_slices):
            rows = group.row_positions[start:end]
            ys = values[rows]
            valid = np.isfinite(ys)
            # Integer mixing is stable across reruns, viewport changes and PCs.
            ids = rows[valid].astype(np.uint64)
            mixed = (ids * np.uint64(2654435761)) % np.uint64(2**32)
            jitter = mixed.astype(float) / 2**32 - 0.5
            center = lot_index + (wafer_index + 0.5) / len(group.wafer_slices)
            xs = center + jitter * 0.72 / len(group.wafer_slices)
            ax.scatter(xs, ys[valid], s=4, alpha=0.45, edgecolors="none",
                       color=_lot_color(lot_index), zorder=1.8)
    # The original figure already accounts for all extrema/specs in full mode
    # and all wafer whiskers in focus mode. Scatter cannot widen the viewport.
    ax.set_ylim(*original_range)
    ax.set_title(ax.get_title().replace("箱体图", "箱线散点图"))
    return fig


def combined_png(cleaned, parameter, spec_info, *, focus=True):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from frontend.charts.lot_scatter import prepare_lot_scatter_groups, _RENDER_LOCK
    with _RENDER_LOCK:
        fig = combined_figure(cleaned, parameter, spec_info, prepare_lot_scatter_groups(cleaned), focus=focus)
        try:
            buffer = BytesIO()
            FigureCanvasAgg(fig).print_png(buffer)
            return buffer.getvalue()
        finally:
            fig.clear()


def render_combined(st, dataset, parameters, get_spec_info):
    if not parameters:
        st.info("cleaned CSV 中没有识别到数值测试参数。")
        return
    full = st.checkbox("显示完整纵轴范围", value=False, key="combined_full_y_range",
                       help="仅改变显示范围；全部有限测量值参与绘图和箱线统计，包含 Fail Bin。")
    cached_png = st.cache_data(show_spinner=False, max_entries=24,
                               hash_funcs={"pandas.core.frame.DataFrame": full_frame_hash})(combined_png)
    for parameter in parameters:
        spec = get_spec_info(dataset.spec, parameter)
        cols = st.columns(4)
        cols[0].metric("参数", parameter)
        cols[1].metric("单位", spec.get("unit") or "N/A")
        cols[2].metric("LSL", "N/A" if spec.get("limit_lower") is None else f"{spec['limit_lower']:g}")
        cols[3].metric("USL", "N/A" if spec.get("limit_upper") is None else f"{spec['limit_upper']:g}")
        # Hash only the columns the chart consumes, rather than every parameter.
        columns = [c for c in ("Lot_ID", "Wafer_ID", parameter) if c in dataset.cleaned]
        st.image(cached_png(dataset.cleaned.loc[:, columns], parameter, spec, focus=not full), width="stretch")


def full_frame_hash(frame):
    """Streamlit samples large frames by default; a chart cache must not do so."""
    import pandas as pd
    h = hashlib.sha256(repr(tuple(zip(frame.columns, map(str, frame.dtypes)))).encode())
    h.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    return h.hexdigest()
