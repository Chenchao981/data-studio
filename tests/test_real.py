"""Real-input boundaries and lossless preview contracts, independent of private data."""
import json
import gzip
import sys
import time
import zipfile
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python_core.core import Core
from python_core.engine import digest
from python_core.result_index import index_artifacts, preview
from python_core.tasks import TaskManager


@pytest.fixture
def kit(tmp_path, monkeypatch):
    from python_core import engine
    root = tmp_path / 'kit'
    (root / 'runtime').mkdir(parents=True)
    (root / 'runtime/python.exe').touch()
    tool = dict(tool_code='TEST_CP', enabled=True, allowed_suffixes=['.csv'],
                display_name='Test', test_stage='CP', factory_code='TEST', analysis_type='QUICK_CLEAN')
    (root / 'manifest.json').write_text(json.dumps(dict(version='test', tools=[tool], files={})), encoding='utf8')
    monkeypatch.setattr(engine, 'engine_root', lambda: root)
    return root


def test_real_requires_explicit_tool_and_registered_nonoverlapping_inputs(tmp_path, kit):
    core = Core(tmp_path / 'workspace')
    p = tmp_path / '晶圆01.csv'; p.write_text('Lot,Wafer\nLOT,01', encoding='utf8')
    source = core.register([str(p)])[0]
    with pytest.raises(ValueError, match='真实文件'): core.create_task(source['id'])
    with pytest.raises(ValueError): core.create_task(source['id'], 'TEST_CP', [source['id'], 'unregistered'])
    task = core.create_task(source['id'], 'TEST_CP')
    assert not task['demo'] and task['engineHash'] == digest(kit / 'manifest.json')
    assert task['sourcePaths'] == [str(p)]
    nested = core.root / 'bad.csv'; nested.touch()
    with pytest.raises(ValueError, match='重叠'): core.create_task(core.register([str(nested)])[0]['id'], 'TEST_CP')
    bad = tmp_path / 'wrong.xlsx'; bad.touch()
    with pytest.raises(ValueError, match='不支持'): core.create_task(core.register([str(bad)])[0]['id'], 'TEST_CP')


def test_worksheet_preserves_identity_units_formula_and_small_values(tmp_path):
    book = openpyxl.Workbook(); sheet = book.active
    sheet.append(['Lot', 'Wafer', 'BVCES1', 'Leakage', 'Formula'])
    sheet.append(['', '', 'V', 'A', None]); sheet.append(['L001', '01', 600.1, 1.2e-12, '=C3*2'])
    source = tmp_path / '源数据.xlsx'; book.save(source)
    folder = tmp_path / 'result'; folder.mkdir()
    tables = index_artifacts(folder, [('result.xlsx', source)])
    page = preview(folder / 'preview.sqlite', tables, dict(dataset='t0', start=0, end=100))
    assert page['total'] == 3 and page['rows'][2]['c1'] == '01'
    assert page['rows'][2]['c3'] == 1.2e-12 and page['rows'][2]['c4'] == '=C3*2'
    assert page['rows'][1]['c2'] == 'V'
    hit = preview(folder / 'preview.sqlite', tables, dict(dataset='t0', search='l001'))
    assert hit['total'] == 1 and hit['rows'][0]['_row'] == 3
    with pytest.raises(ValueError): preview(folder / 'preview.sqlite', tables, dict(dataset='t0', end=201))
    with pytest.raises(ValueError): preview(folder / 'preview.sqlite', tables, dict(dataset='t0', sort=[{}]))


def test_zip_csv_full_preview_and_reject_invalid_member(tmp_path):
    source = tmp_path / 'result.zip'
    with zipfile.ZipFile(source, 'w') as z:
        z.writestr('数据/clean.csv', 'Lot,Wafer\n' + 'L001,01\n' * 400)
        z.writestr('数据/clean.csv.gz', gzip.compress(b'Lot,Wafer\nL001,01\n'))
    folder = tmp_path / 'preview'; folder.mkdir()
    tables = index_artifacts(folder, [('result.zip', source)])
    page = preview(folder / 'preview.sqlite', tables, dict(dataset='t0', start=390, end=490))
    assert page['total'] == 401 and len(page['rows']) == 11
    assert all(row['c1'] == '01' for row in page['rows'])
    assert preview(folder / 'preview.sqlite', tables, dict(dataset='t1'))['rows'][1]['c1'] == '01'
    bad = tmp_path / 'bad.zip'
    with zipfile.ZipFile(bad, 'w') as z: z.writestr('../escaped.csv', 'invalid')
    other = tmp_path / 'other'; other.mkdir()
    with pytest.raises(ValueError, match='无效路径'): index_artifacts(other, [('bad.zip', bad)])


def test_real_history_reopen_and_preview_tamper(tmp_path):
    core = Core(tmp_path / 'workspace'); task = core.create_task('demo-cp')
    folder = core.results / task['id']; folder.mkdir()
    csv = folder / 'data.csv'; csv.write_text('Wafer\n01\n', encoding='utf8')
    tables = index_artifacts(folder, [('data.csv', csv)])
    task.update(demo=False, status='SUCCESS', output=str(csv), sha256=digest(csv), tables=tables,
                previewHash=digest(folder / 'preview.sqlite'), artifacts=[dict(path=str(csv), sha256=digest(csv))])
    core.save_task(task); again = Core(core.root)
    request = dict(taskId=task['id'], dataset='t0')
    assert again.real_preview(request)['rows'][1]['c0'] == '01'
    assert again.output(task['id']) == csv and again.artifact(task['id'], 0) == csv
    (folder / 'preview.sqlite').write_bytes(b'changed')
    with pytest.raises(ValueError, match='改变'): again.real_preview(request)
    csv.write_text('changed', encoding='utf8')
    with pytest.raises(ValueError): again.followup(task['id'])
    with pytest.raises(ValueError): again.artifact(task['id'], 0)


def test_real_cancel_reaps_owned_process_without_publishing(tmp_path, kit):
    core = Core(tmp_path / 'workspace'); source = tmp_path / 'input.csv'; source.write_text('test')
    task = core.create_task(core.register([str(source)])[0]['id'], 'TEST_CP')
    manager = TaskManager(core)
    try:
        manager.start(task['id']); manager.tick(); manager.cancel(task['id'])
        deadline = time.monotonic() + 30
        while manager.active and time.monotonic() < deadline:
            manager.tick(); time.sleep(.05)
        assert manager.active is None and core.task(task['id'])['status'] == 'CANCELLED'
        with pytest.raises(ValueError): core.output(task['id'])
        assert source.read_text() == 'test'
    finally: manager.close()
