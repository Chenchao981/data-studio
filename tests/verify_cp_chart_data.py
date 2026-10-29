"""Reconcile every CP plot value/box and a downloaded Cpk against pinned code.

Use private real-task homes. Also compare CP CSVs and FT workbook cells with a
previous release's private verification home; report paths stay local.
"""
import argparse
import ast
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engines/packages/cp.pyz'), str(ROOT/'engine_support/desktop_client')]


def outputs(home, stage):
    for p in (home/'results').glob('*/outcome.json'):
        task = json.loads(p.read_text(encoding='utf8'))
        if task.get('receipt', {}).get('stage') == stage and task['status'] == 'SUCCESS':
            return [Path(a['path']) for a in task['artifacts']]
    raise ValueError('Missing successful '+stage+' result')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--browser', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import math
    import numpy as np
    import pandas as pd
    import openpyxl
    from frontend.charts.lot_scatter import prepare_lot_scatter_groups, _make_lot_boxplot_figure
    from nce_desktop.cp_chart_controls import combined_figure
    from hashlib import file_digest
    package = ROOT/'engines/packages/cp.pyz'
    with package.open('rb') as f:
        assert file_digest(f, 'sha256').hexdigest() == json.loads((ROOT/'engine-pins.json').read_text())['cp']
    with zipfile.ZipFile(package) as z:
        source = z.read('frontend/cp_dashboard_app.py').decode()
    names = ('get_spec_info', 'normalize_spec_info', 'cpk_table')
    functions = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
    future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
    ns = dict(pd=pd, np=np, math=math)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, *functions], type_ignores=[])), '<pinned-cp>', 'exec'), ns)
    def cp_data(home):
        files = outputs(home, 'CP')
        clean = next(p for p in files if '_cleaned_' in p.name and p.suffix == '.csv')
        spec = next(p for p in files if '_spec_' in p.name and p.suffix == '.csv')
        return pd.read_csv(clean, dtype={'Lot_ID': str, 'Wafer_ID': str}), pd.read_csv(spec)
    new, spec = cp_data(args.home)
    old, old_spec = cp_data(args.reference)
    pd.testing.assert_frame_equal(new, old)
    pd.testing.assert_frame_equal(spec, old_spec)
    downloaded = pd.read_csv(args.browser/'cpk.csv')
    expected = ns['cpk_table'](new, spec, list(downloaded['参数']))
    pd.testing.assert_frame_equal(expected, downloaded, check_dtype=False, rtol=1e-12)
    groups = prepare_lot_scatter_groups(new)
    report = {}
    # This real HuaHong fixture has the matrix spec contract, not guessed columns.
    assert spec.columns[0] == 'Parameter' and 'Unit' in set(spec.iloc[:, 0])
    for parameter in spec.columns[1:]:
        numeric = pd.to_numeric(new[parameter], errors='coerce').to_numpy(float)
        finite = numeric[np.isfinite(numeric)]
        info = ns['get_spec_info'](spec, parameter)
        before = _make_lot_boxplot_figure(new, parameter, info, groups, focus=True)
        after = combined_figure(new, parameter, info, groups, focus=True)
        try:
            points = np.concatenate([c.get_offsets() for c in after.axes[0].collections])
            np.testing.assert_array_equal(np.sort(points[:, 1]), np.sort(finite))
            np.testing.assert_array_equal(before.axes[0].get_ylim(), after.axes[0].get_ylim())
            for a, b in zip(before.axes[0].lines, after.axes[0].lines, strict=True):
                np.testing.assert_array_equal(a.get_ydata(), b.get_ydata())
            report[parameter] = dict(finiteCount=len(finite), waferBoxes=len(after.axes[0].patches), spec=info)
        finally:
            before.clear(); after.clear()
    def ft_book(home):
        return openpyxl.load_workbook(next(p for p in outputs(home, 'FT') if p.suffix == '.xlsx'), read_only=True, data_only=True)
    a, b = ft_book(args.home), ft_book(args.reference)
    try:
        assert a.sheetnames == b.sheetnames
        rows = 0
        for sheet in a.sheetnames:
            for x, y in zip(a[sheet].iter_rows(values_only=True), b[sheet].iter_rows(values_only=True), strict=True):
                assert x == y
                rows += 1
    finally:
        a.close(); b.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(status='PASS', CPRecords=len(new), CPParameters=len(report),
        priorCPOutputIdentical=True, downloadedCpkMatchesOriginal=True, allParameters=report,
        FTCellsIdentical=True, FTRowsIncludingHeader=rows), ensure_ascii=False, indent=2), encoding='utf8')
    print('PASS: all CP values/boxes/specs, downloaded Cpk, previous CP output and FT cells; FT rows including header:', rows)


if __name__ == '__main__':
    main()
