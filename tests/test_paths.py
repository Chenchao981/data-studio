import csv
import json
import threading
from pathlib import Path
import pytest
from python_core.core import Core
from python_core.engine import digest
from python_core.publishing import publish
from python_core.results import directory,export_folder


def test_paths_persist_reopen_and_deleted_location_falls_back(tmp_path,monkeypatch):
    desktop=tmp_path/'Desktop';desktop.mkdir()
    monkeypatch.setattr('python_core.paths.desktop_directory',lambda:str(desktop))
    core=Core(tmp_path/'history');assert core.settings()['outputDirectory']==str(desktop)
    folder=tmp_path/'input';folder.mkdir();file=folder/'wafer.TXT';file.write_text('raw')
    inputs=core.register([str(file),str(folder)])
    assert [f['folder'] for f in inputs]==[False,True]
    output=tmp_path/'output';output.mkdir();core.set_output_directory(str(output))
    again=Core(core.root)
    assert again.settings()['inputDirectory']==str(folder)
    assert again.settings()['inputIds']==[f['id'] for f in inputs]
    assert again.settings()['outputDirectory']==str(output)
    with pytest.raises(FileNotFoundError):again.register([str(file),str(tmp_path/'missing')])
    assert again.settings()['inputIds']==[f['id'] for f in inputs]
    file.unlink();folder.rmdir();output.rmdir()
    state=Core(core.root).settings()
    assert state['inputDirectory']==str(desktop) and state['outputDirectory']==str(output) and state['inputIds']==[]


def task_fixture(tmp_path):
    core=Core(tmp_path/'history');task=core.create_task('demo-cp')
    folder=core.results/task['id']/'files'/'LOT_20261027_120000';folder.mkdir(parents=True)
    paths=[]
    for kind in ('cleaned','yield','spec'):
        path=folder/('LOT_'+kind+'_20261027.csv');path.write_text('Lot_ID,Wafer_ID,V\nLOT,001,1e-08\n')
        paths.append({'name':'files/'+folder.name+'/'+path.name,'path':str(path),'sha256':digest(path)})
    raw=tmp_path/'raw';raw.mkdir();out=tmp_path/'output';out.mkdir()
    task.update(demo=False,status='SUCCESS',finished='2026-10-27T01:02:03+00:00',parameters={'stage':'CP','factory':'HUAHONG'},sourcePaths=[str(raw)],outputParent=str(out),artifacts=paths)
    core.save_task(task)
    return core,task


def test_publish_original_files_collision_and_history_remains_independent(tmp_path):
    core,task=task_fixture(tmp_path);event=threading.Event()
    first=publish(task,core.root,event);second=publish(task,core.root,event)
    assert Path(first['publishedDirectory']).name=='LOT_20261027_120000'
    assert Path(second['publishedDirectory']).name=='LOT_20261027_120000_001'
    assert len(list(Path(first['publishedDirectory']).iterdir()))==3
    for item in task['artifacts']:
        assert digest(Path(first['publishedDirectory'])/Path(item['path']).name)==item['sha256']
    task.update(first);core.save_task(task)
    assert directory(core,task['id'])==Path(first['publishedDirectory'])
    # Editing an external copy never changes historical data or re-export.
    next(Path(first['publishedDirectory']).iterdir()).write_text('user edited')
    more=tmp_path/'another';more.mkdir();saved=Path(export_folder(core,task['id'],more))
    for item in task['artifacts']:assert digest(saved/Path(item['path']).name)==item['sha256']


def test_publish_cancellation_tamper_and_bad_targets_leave_no_partial_result(tmp_path):
    core,task=task_fixture(tmp_path);event=threading.Event();event.set()
    with pytest.raises(InterruptedError):publish(task,core.root,event)
    assert not list(Path(task['outputParent']).iterdir())
    event.clear();Path(task['artifacts'][0]['path']).write_text('tampered')
    with pytest.raises(ValueError,match='改变'):publish(task,core.root,event)
    assert not list(Path(task['outputParent']).iterdir())
    for destination in (core.root,Path(task['sourcePaths'][0])):
        with pytest.raises(ValueError):publish({**task,'outputParent':str(destination)},core.root,event)


def test_shared_report_zip_is_saved_without_unpacking_or_changing(tmp_path):
    core,task=task_fixture(tmp_path);report=core.results/task['id']/'report.zip';report.write_bytes(b'original report bytes')
    task['artifacts']=[dict(name='report.zip',path=str(report),sha256=digest(report))]
    saved=publish(task,core.root,threading.Event())
    assert (Path(saved['publishedDirectory'])/'report.zip').read_bytes()==report.read_bytes()
