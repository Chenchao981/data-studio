"""Lazy chart execution and redraw contracts, against the actual pinned CP source."""
import ast
from contextlib import nullcontext
from pathlib import Path
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine_support/desktop_client'))
from nce_desktop.cp_chart_controls import adapt_dashboard, selected_tabs, COMBINED, OPTIONAL


@pytest.fixture
def dashboard(tmp_path):
    package = ROOT / 'engines/packages/cp.pyz'
    if not package.is_file():
        pytest.skip('Requires the pinned CP package; see TEST-ENTRYPOINTS.md')
    script = tmp_path / 'dashboard.py'
    with zipfile.ZipFile(package) as z:
        script.write_bytes(z.read('frontend/cp_dashboard_app.py'))
    return script


def main_tree(script):
    return next(n for n in ast.parse(script.read_text(encoding='utf8')).body
                if isinstance(n, ast.FunctionDef) and n.name == 'main')


def test_unselected_charts_never_execute(dashboard):
    adapt_dashboard(dashboard)
    main = main_tree(dashboard)
    start = next(i for i,n in enumerate(main.body) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'tabs' for t in n.targets))
    suffix = ast.Module(body=main.body[start:], type_ignores=[])
    calls = []
    class ST:
        def tabs(self, labels):
            calls.append(('tabs', labels))
            return [nullcontext() for _ in labels]
        def markdown(self, *a, **kw): pass
    namespace = dict(st=ST(), applied_filters={'charts': []},
                     _studio_tabs=selected_tabs, _studio_combined=lambda *a: calls.append('combined'),
                     dataset=None, params=['P'], get_spec_info=None)
    # Optional bodies intentionally have no functions/data in scope. Even one
    # eager call would fail, including tables, Mapping, statistics and PNGs.
    exec(compile(suffix, str(dashboard), 'exec'), namespace)
    assert calls == [('tabs', [COMBINED]), 'combined']
    calls.clear()
    namespace.update(applied_filters={'charts': [OPTIONAL[0]]},
                     summary={'bin_counts': {}, 'total_die': 7},
                     render_bin_grid=lambda *a: calls.append('bin-grid'),
                     bin_pareto_chart=lambda *a: calls.append('bin-figure'),
                     render_plotly_chart=lambda *a: calls.append('plotly'))
    exec(compile(suffix, str(dashboard), 'exec'), namespace)
    assert calls == [('tabs', [COMBINED, OPTIONAL[0]]), 'combined', 'bin-grid', 'bin-figure', 'plotly']


def test_drafts_apply_only_on_redraw(dashboard):
    adapt_dashboard(dashboard)
    main = main_tree(dashboard)
    draft_index = next(i for i,n in enumerate(main.body) if isinstance(n, ast.Assign)
                       and ast.unparse(n.targets[0]) == 'draft_filters')
    applied_index = next(i for i,n in enumerate(main.body) if isinstance(n, ast.Assign)
                         and ast.unparse(n.targets[0]) == 'applied_filters')
    logic = ast.Module(body=main.body[draft_index:applied_index+1], type_ignores=[])
    class ST:
        session_state = None
        def form_submit_button(self, *a, **kw): return self.draw
    st = ST(); st.session_state = {}; st.draw = False
    ns = dict(st=st, _studio_chart_form=st, render_token='same-dataset', selected_lots=['L'],
              selected_wafer_labels=['L / W01'], params=['P'], selected_extra_charts=[],
              pass_bin=1, max_points=8000, render_file_status=lambda *a: None, dataset=None)
    exec(compile(logic, str(dashboard), 'exec'), ns)
    initial = ns['applied_filters']
    assert initial['charts'] == []
    ns.update(selected_extra_charts=[OPTIONAL[5]], params=['P', 'Q'], pass_bin=2)
    exec(compile(logic, str(dashboard), 'exec'), ns)
    assert ns['applied_filters'] == initial and ns['draft_filters'] != initial
    st.draw = True
    exec(compile(logic, str(dashboard), 'exec'), ns)
    assert ns['applied_filters'] == ns['draft_filters']
    assert ns['applied_filters']['charts'] == [OPTIONAL[5]]
    assert ns['applied_filters']['parameters'] == ['P', 'Q']
    st.draw = False; ns['selected_extra_charts'] = []
    exec(compile(logic, str(dashboard), 'exec'), ns)
    assert ns['applied_filters']['charts'] == [OPTIONAL[5]]
    st.draw = True
    exec(compile(logic, str(dashboard), 'exec'), ns)
    assert ns['applied_filters']['charts'] == []


def test_changed_layout_rejected(dashboard):
    source = dashboard.read_text(encoding='utf8').replace('📋 Pareto', 'new layout')
    dashboard.write_text(source, encoding='utf8')
    with pytest.raises(ValueError, match='适配'):
        adapt_dashboard(dashboard)
    assert dashboard.read_text(encoding='utf8') == source


def test_combined_preserves_all_values_identity_statistics_and_viewport(monkeypatch):
    import numpy as np
    import pandas as pd
    monkeypatch.syspath_prepend(str(ROOT / 'engines/packages/cp.pyz'))
    from frontend.charts.lot_scatter import prepare_lot_scatter_groups, _make_lot_boxplot_figure
    from nce_desktop.cp_chart_controls import combined_figure, combined_png
    frame = pd.DataFrame({'Lot_ID': ['A']*8+['B']*4,
                          'Wafer_ID': ['01']*4+['1']*4+['01']*4,
                          'P': [1., 2., 2., 90., np.nan, np.inf, 3., 4., -1., 0., 1., -np.inf],
                          'Bin': [1, 2]*6})
    groups = prepare_lot_scatter_groups(frame)
    assert [label for g in groups for _, label in g.wafer_ticks] == ['01', '1', '01']
    spec = dict(unit='V', limit_lower=-5, limit_upper=100)
    expected = np.sort(frame.P.to_numpy()[np.isfinite(frame.P)])
    for focus in (True, False):
        original = _make_lot_boxplot_figure(frame, 'P', spec, groups, focus=focus)
        combined = combined_figure(frame, 'P', spec, groups, focus=focus)
        try:
            ax = combined.axes[0]
            points = np.concatenate([c.get_offsets() for c in ax.collections])
            np.testing.assert_array_equal(np.sort(points[:, 1]), expected)
            assert len(ax.patches) == 3
            np.testing.assert_array_equal(ax.get_ylim(), original.axes[0].get_ylim())
            # Boxes, medians, whiskers and specification lines are untouched.
            for before, after in zip(original.axes[0].lines, ax.lines, strict=True):
                np.testing.assert_array_equal(before.get_ydata(), after.get_ydata())
            assert '箱线散点图' in ax.get_title()
        finally:
            original.clear(); combined.clear()
    assert combined_png(frame, 'P', spec).startswith(b'\x89PNG\r\n\x1a\n')


def test_cache_hash_covers_middle_of_large_frame():
    import pandas as pd
    from nce_desktop.cp_chart_controls import full_frame_hash
    frame = pd.DataFrame({'Lot_ID': ['A']*60001, 'Wafer_ID': ['01']*60001, 'P': range(60001)})
    initial = full_frame_hash(frame)
    frame.loc[30001, 'P'] = -123456
    assert full_frame_hash(frame) != initial
