"""Exercise actual chart entry points, not just the name matching helper."""
import ast
import copy
from pathlib import Path
import sys
from types import ModuleType
import zipfile

import pandas as pd
import pytest

from nce_desktop.parameter_visibility import (
    analysis_parameter_result, is_analysis_parameter, visible_parameter_names,
)
from nce_desktop.cp_chart_controls import adapt_dashboard

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name', ['CONT', 'CONT_TD', 'CONT@G', 'CONT@S',
    'CONT@Gref', 'CONT2', 'CONT1(p)', ' cont (V) ', 'ＣＯＮＴ＠Ｄ'])
def test_control_variants_are_hidden(name):
    assert not is_analysis_parameter(name)


def test_real_names_order_and_values_are_not_normalized_or_deduplicated():
    names = ['CONTENT', 'VTH', 'VTH', 'DISCONT', 'CONTINUITY', 'VSAME', ' BVDSS(V) ']
    assert visible_parameter_names(names) == names
    assert visible_parameter_names(['CONT@G', *names, 'CONT2']) == names


def test_cp_actual_selector_and_old_applied_selection(tmp_path):
    with zipfile.ZipFile(ROOT/'engines/packages/cp.pyz') as z:
        script = tmp_path/'cp_dashboard_app.py'
        script.write_bytes(z.read('frontend/cp_dashboard_app.py'))
        stats_source = z.read('frontend/charts/parameter_statistics.py').decode('utf8')
    adapt_dashboard(script)
    tree = ast.parse(script.read_text(encoding='utf8'))
    spec_tree = ast.parse(stats_source)
    nodes = [n for n in spec_tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == 'PROCESS_COLUMNS' for t in n.targets)]
    nodes += [n for n in spec_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'spec_parameters']
    nodes += [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'available_parameters']
    future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
    ns = dict(pd=pd, BASE_COLUMNS={'Lot_ID', 'Wafer_ID'},
              _studio_analysis_names=analysis_parameter_result,
              _studio_visible_names=visible_parameter_names)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[])), '<selector>', 'exec'), ns)
    data = pd.DataFrame({'CONT@G': [0., 1.]*3, 'VTH': [1.2, 1.4]*3, 'CONTENT': [5., 6.]*3})
    spec = pd.DataFrame({'Parameter': ['Unit','LimitL','LimitU'],
                         'CONT@G': ['V',-1,1], 'VTH': ['V',1,2], 'CONTENT': ['A',0,9]})
    before, spec_before = data.copy(deep=True), spec.copy(deep=True)
    assert ns['available_parameters'](data, spec) == ['VTH', 'CONTENT']
    assert ns['available_parameters'](data) == ['VTH', 'CONTENT']
    assert ns['available_parameters'](data[['CONT@G']], spec[['Parameter','CONT@G']]) == []
    # Saved selections from an already-open chart must not reintroduce CONT.
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    assign = next(n for n in main.body if isinstance(n, ast.Assign)
                  and ast.unparse(n.value) == "_studio_visible_names(applied_filters['parameters'])")
    ns['applied_filters'] = {'parameters': ['CONT@G', 'VTH']}
    exec(compile(ast.Module(body=[assign], type_ignores=[]), '<applied>', 'exec'), ns)
    assert ns['params'] == ['VTH']
    pd.testing.assert_frame_equal(data, before)
    pd.testing.assert_frame_equal(spec, spec_before)


@pytest.mark.parametrize('names, expected', [
    (['CONT2', 'VTH', 'CONT@G', 'CONTENT'], ['VTH', 'CONTENT']),
    (['CONT@G'], []),
])
def test_ft_entry_filters_before_rendering_and_preserves_source(tmp_path, monkeypatch, names, expected):
    from nce_desktop import local_ft_charts
    meta = {'parameters': names[:]}
    data, spec = pd.DataFrame({name: [1., 2.] for name in names}), object()
    data_before = data.copy(deep=True)
    original = copy.deepcopy(meta)
    rendered = []
    class Cleaner:
        def __init__(self, *args, **kwargs): self.last_scatter_manifest = 'manifest'
        def process_all(self): return True
    def renderer(actual_data, actual_spec, name, layout, **kwargs):
        assert actual_data is data and actual_spec is spec
        rendered.append(name)
        return b'png', {'parameter': name}
    modules = {
        'factories.dianji.dc_cleaner': dict(DianjiDCCleaner=Cleaner),
        'frontend.ft_scatter': dict(load_scatter_bundle=lambda _: (meta, data, spec)),
        'frontend.ft_static_charts': dict(prepare_ft_chart_layout=lambda _: None,
            render_ft_scatter_png=renderer, render_ft_boxplot_png=renderer,
            safe_png_name=lambda name, kind: name+kind+'.png'),
    }
    for name, contents in modules.items():
        module = ModuleType(name); module.__dict__.update(contents)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(sys, 'argv', ['chart', str(tmp_path), 'DIANJI', str(tmp_path), str(tmp_path), str(tmp_path)])
    monkeypatch.setattr(sys, 'path', sys.path[:])
    if expected:
        local_ft_charts.main()
        assert rendered == [name for name in expected for _ in range(4)]
        assert len(list(tmp_path.glob('*.png'))) == 4*len(expected)
    else:
        with pytest.raises(ValueError, match='没有可绘图'):
            local_ft_charts.main()
        assert not rendered
    assert meta == original
    pd.testing.assert_frame_equal(data, data_before)
