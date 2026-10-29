"""Exercise the bundled CP reader + FT PAT engine, not a duplicate formula implementation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[3]
KIT = ROOT / 'engines'
SUPPORT = ROOT / 'engine_support'
pytestmark = pytest.mark.skipif(not (KIT / 'runtime/python.exe').exists(), reason='pinned local runtime required')


def source(folder, station='203', upper='50nA', name='wafer.TXT', *, product='NCEVTG120EV60DA', values=None):
    folder.mkdir(parents=True, exist_ok=True)
    batch = product + '_FA69-9001@' + station
    values = values if values is not None else [1,2,3,4,100]
    text = '\n'.join([
        'Program name\tTEST_' + station + '.dll', 'Lot number\tFA69-9001-363A-261028@' + station,
        'Wafer number\t01', 'Date\t2026/10/28', 'Time\t12:00:00', '',
        'No.U\tX\tY\tBin\tVTH1\tIGES1', 'LimitU\t\t\t\t5V\t' + upper,
        'LimitL\t\t\t\t0V\t0nA',
        *[f'Bias {i}\t\t\t\t \t ' for i in range(1, 7)],
        *[f'{i}\t{i}\t1\t{2 if v >= 100 else 1}\t{v}\t{v * 1e-9}' for i, v in enumerate(values, start=1)]
    ])
    path = folder / (batch + '.zip')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(name, text)
    return path


def run(folder, out):
    out.mkdir()
    package = KIT / 'packages/native.pyz'
    env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8',
           'STUDIO_FT_PAT_PACKAGE': str(package), 'STUDIO_FT_PAT_SHA256': hashlib.sha256(package.read_bytes()).hexdigest()}
    return subprocess.run([str(KIT / 'runtime/python.exe'), '-s', '-B',
        str(SUPPORT / 'desktop_client/nce_desktop/local_native_worker.py'), str(KIT / 'packages/cp.pyz'),
        'LOCAL_CP_HUAHONG_RAW_PAT_V1', json.dumps([str(folder)]), str(out)],
        env=env, encoding='utf-8', capture_output=True, timeout=90)


def test_product_name_and_complete_batch_are_explicit():
    sys.path.insert(0, str(SUPPORT / 'desktop_client'))
    from nce_desktop.local_cp_pat import parse_batch_name
    assert parse_batch_name('NCEVTG120EV60DA_FA69-9491@203') == ('NCEVTG120EV60DA', 'FA69-9491', '203')
    with pytest.raises(ValueError, match='批次名称'):
        parse_batch_name('FA69-9491@203')


def test_one_excel_per_product_pools_raw_values_across_stations(tmp_path):
    inputs = tmp_path / 'raw'
    source(inputs, '203'); source(inputs, '202', values=[11,12,13,14,110])
    source(inputs, product='NCEOTHER')
    done = run(inputs, tmp_path / 'result')
    assert done.returncode == 0, done.stdout + done.stderr
    manifest = json.loads((tmp_path / 'result/PAT_source_manifest.json').read_text(encoding='utf8'))
    assert manifest['group_by'] == 'product'
    assert [(g['product'], g['record_count'], g['parameter_count']) for g in manifest['groups']] == [('NCEOTHER', 5, 2), ('NCEVTG120EV60DA', 10, 2)]
    published = list((tmp_path / 'result/files').iterdir())
    assert len(published) == 2 and all(p.is_file() and p.suffix == '.xlsx' for p in published)
    for group in manifest['groups']:
        book = openpyxl.load_workbook(tmp_path / 'result/files' / group['report'], data_only=True)
        assert book.sheetnames == ['PAT']
        rows = list(book.active.values)
        assert len(rows) == 4 and len(rows[0]) == 17 and rows[1][0] == '变量'
        count, median, maximum, iqr = (10, 11.5, 110, 10.5) if group['product']=='NCEVTG120EV60DA' else (5, 3, 100, 2)
        for row in rows[2:]:
            assert row[1] == count and row[6] == median and row[8] == maximum  # keep Bin 2 / raw outlier
            assert row[9] == pytest.approx(iqr/1.35, abs=1e-6)
            assert row[10] == pytest.approx(median-6*iqr/1.35, abs=1e-6)
            assert row[11] == pytest.approx(median+6*iqr/1.35, abs=1e-6)
            assert row[14:] == (None, None, None)
        assert rows[3][0] == 'IGES1 (nA)' and rows[3][12:14] == (0, 50)
        book.close()


def test_duplicate_wafer_same_population_rejected(tmp_path):
    inputs = tmp_path / 'raw'
    source(inputs / 'first'); source(inputs / 'copy')
    done = run(inputs, tmp_path / 'result')
    assert done.returncode != 0 and '同一批次与片号重复' in done.stderr
    assert not list((tmp_path / 'result').rglob('*.xlsx'))


@pytest.mark.parametrize('other_station', ['202', '203'])
def test_different_specs_same_product_rejected(tmp_path, other_station):
    inputs = tmp_path / 'raw'
    first = source(inputs)
    second = inputs / ('NCEVTG120EV60DA_FA69-9002@' + other_station + '.zip')
    with zipfile.ZipFile(first) as z:
        text = z.read('wafer.TXT').decode().replace('FA69-9001', 'FA69-9002').replace('50nA', '60nA').replace('203', other_station)
    with zipfile.ZipFile(second, 'w') as z:
        z.writestr('wafer.TXT', text)
    done = run(inputs, tmp_path / 'result')
    assert done.returncode != 0 and '不同规格' in done.stderr
    assert not list((tmp_path / 'result').rglob('*.xlsx'))
