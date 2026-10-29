import json
import os
from pathlib import Path

import pytest

from python_core.core import Core
from python_core import engine


def test_catalog_cache_refreshes_when_manifest_changes(tmp_path,monkeypatch):
    (tmp_path/'runtime').mkdir();(tmp_path/'runtime/python.exe').touch()
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'version':'one','tools':[]}))
    monkeypatch.setattr(engine,'engine_root',lambda:tmp_path)
    engine._catalog.cache_clear()
    assert engine.catalog()['version']=='one'
    assert engine.catalog()['version']=='one'
    assert engine._catalog.cache_info().hits==1
    stamp=manifest.stat().st_mtime_ns
    manifest.write_text(json.dumps({'version':'two','tools':[{'tool_code':'new'}]}))
    os.utime(manifest,ns=(stamp+1000000,stamp+1000000))
    assert engine.catalog()['version']=='two'
    assert engine.catalog()['tools'][0]['tool_code']=='new'
    manifest.unlink()
    assert not engine.catalog()['ready']


def test_history_filters_before_limit_and_can_find_old_factory(tmp_path):
    core=Core(tmp_path)
    for i in range(130):
        task=dict(id=str(i),name='test',parser='华虹 TD' if i else '电基 FT',status='SUCCESS' if i else 'FAILED',parameters={'stage':'CP' if i else 'FT'})
        core.save_task(task)
    assert len(core.history())==100
    assert [t['id'] for t in core.history('', 'FT','FAILED')]==['0']
    assert [t['id'] for t in core.history('电基')]==['0']
    assert core.history('', 'CP','FAILED')==[]
    with pytest.raises(ValueError):core.history('',"CP' OR 1=1",'')


def test_recent_imports_remain_visible_and_old_ids_stay_registered(tmp_path):
    core=Core(tmp_path)
    with core.connect() as con:
        for i in range(1010):
            row=dict(id=str(i),name=f'{i}.xlsx',demo=False,path=str(tmp_path/f'{i}.xlsx'))
            con.execute('INSERT INTO sources VALUES (?,?)',(str(i),json.dumps(row)))
    rows=core.files()
    assert len(rows)==1003
    assert '1009' in {r['id'] for r in rows} and '0' not in {r['id'] for r in rows}
    assert core.registered_sources(['0','1009','unknown']).keys()=={'0','1009'}
